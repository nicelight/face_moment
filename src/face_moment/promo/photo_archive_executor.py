"""One backend-local ZIP executor; orders are its only durable queue.

@docs .memory-bank/domains/photo-orders.md#исполнение-и-выдача
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from io import BytesIO
import logging
import threading
import uuid
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from face_moment.infrastructure.archive_failure_mail import ArchiveFailureMail
from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.inventory.public_photo_projection import read_public_active_original
from face_moment.promo.photo_orders import PhotoOrder

logger = logging.getLogger(__name__)
ARCHIVE_FAILURE_REASON = 'Не удалось подготовить архив. Обратитесь в поддержку.'


class PhotoArchiveExecutor:
    def __init__(self, session_factory: Callable[[], Session], store: PrivateObjectStore,
                 mail: ArchiveFailureMail, *, idle_seconds: float = .2) -> None:
        self.session_factory = session_factory
        self.store = store
        self.mail = mail
        self.idle_seconds = idle_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='photo-archive', daemon=True)

    def start(self) -> None:
        # Called outside the ASGI event loop; no job table or Photo-worker work.
        with self.session_factory() as session, session.begin():
            session.execute(update(PhotoOrder).where(PhotoOrder.archive_status == 'preparing')
                            .values(archive_status='requested'))
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                processed = self._prepare_oldest()
            except Exception:
                # Operational infrastructure failure, no secret/key/error text.
                logger.error('photo_archive_executor_unavailable')
                processed = False
            if not processed:
                self._stop.wait(self.idle_seconds)

    def _prepare_oldest(self) -> bool:
        with self.session_factory() as session, session.begin():
            order = session.scalar(select(PhotoOrder).where(PhotoOrder.archive_status == 'requested')
                .order_by(PhotoOrder.created_at, PhotoOrder.id).limit(1).with_for_update())
            if order is None:
                return False
            identity = order.id
            items = list(order.items)
            order.archive_status = 'preparing'
            order.archive_failure_reason = None
        final_key = f'photo-archives/{identity}/selected.zip'
        temporary_key = f'photo-archives/{identity}/building.zip'
        try:
            body = BytesIO()
            with ZipFile(body, 'w', compression=ZIP_DEFLATED) as archive:
                for item in items:
                    photo_id = uuid.UUID(item['photo_id'])
                    with self.session_factory() as session:
                        key = read_public_active_original(session, photo_id=photo_id,
                            venue_ids=(uuid.UUID(item['venue_id']),))
                    if key is None:
                        raise FileNotFoundError('Selected original unavailable')
                    archive.writestr(f'{photo_id}.jpg', self.store.read(key=key))
            data = body.getvalue()
            self.store.put(key=temporary_key, body=data)
            self.store.put(key=final_key, body=self.store.read(key=temporary_key))
            with self.session_factory() as session, session.begin():
                record = session.get(PhotoOrder, identity, with_for_update=True)
                if record is None:
                    raise RuntimeError('Order disappeared')
                record.archive_status = 'ready'
                record.archive_object_key = final_key
                if record.ready_at is None:
                    record.ready_at = datetime.now(timezone.utc)
        except Exception:
            with self.session_factory() as session, session.begin():
                record = session.get(PhotoOrder, identity, with_for_update=True)
                if record is not None:
                    record.archive_status = 'failed'
                    record.archive_failure_reason = ARCHIVE_FAILURE_REASON
                    record.archive_object_key = None
            try:
                self.mail.notify(identity)
            except Exception:
                logger.error('photo_archive_failure_mail_failed order_id=%s', identity)
        finally:
            try:
                self.store.delete(key=temporary_key)
            except Exception:
                logger.error('photo_archive_temporary_cleanup_failed order_id=%s', identity)
        return True
