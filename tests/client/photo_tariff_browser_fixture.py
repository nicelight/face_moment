"""Disposable native staff/API browser fixture; no operator DB writes."""
import json
import socket
import sys
import threading

import uvicorn
from sqlalchemy.orm import Session

from face_moment.entrypoints.backend import create_app
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from tests.disposable_postgresql import disposable_postgresql_engine

with disposable_postgresql_engine('task130_browser') as engine:
    app = create_app()
    app.state.role_state['session_factory'] = lambda: Session(engine)
    for role in (StaffRole.OPERATOR, StaffRole.DEVELOPER):
        with Session(engine) as session:
            provision_staff_user(session, username=f'tariff-{role.value}',
                                 password='browser-fixture-password', role=role)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(128)
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
        worker = threading.Thread(target=server.run, kwargs={'sockets': [listener]})
        worker.start()
        print(json.dumps({'url': f'http://127.0.0.1:{listener.getsockname()[1]}'}), flush=True)
        try:
            sys.stdin.readline()
        finally:
            server.should_exit = True
            worker.join(timeout=15)
print('DISPOSABLE_DB_CLEANED', flush=True)
