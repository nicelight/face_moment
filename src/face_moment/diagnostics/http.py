"""Thin HTTP adapter for diagnostics-owned staff Attempt investigation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from html import escape
import json
import uuid

from fastapi import Cookie, FastAPI, Request, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from face_moment.diagnostics.attempt_investigation import (
    AttemptInvestigationAccessDeniedError,
    AttemptInvestigationNotFoundError,
    AttemptInvestigationView,
    authorize_attempt_investigation,
    read_attempt_detail,
    read_attempts,
)
from face_moment.platform.auth.sessions import InvalidSessionError, get_current_principal
from face_moment.promo.attempt_queries import (
    AttemptInvestigationFilters,
    AttemptProcessingStatus,
)


_NO_STORE_HEADERS = {"Cache-Control": "no-store"}
_FILTER_NAMES = frozenset({"attempt_id", "correlation_id", "from", "to", "state"})
_STATES = frozenset(
    {
        "accepted",
        "searching",
        "result_issued",
        "no_success",
        "interrupted",
        "deadline",
        "internal_failure",
    }
)


class InvalidAttemptInvestigationFilterError(ValueError):
    """The list query is outside the exact bounded filter contract."""


def register_attempt_investigation_routes(
    app: FastAPI, *, session_factory: Callable[[], Session]
) -> None:
    @app.get("/staff/attempts", response_class=HTMLResponse)
    def attempt_list(
        request: Request,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> Response:
        try:
            with _database_session(session_factory) as database_session:
                principal = get_current_principal(
                    database_session, session_token=fm_staff_session
                )
                filters = parse_attempt_filters(request)
                views = read_attempts(
                    database_session,
                    principal=principal,
                    filters=filters,
                )
                content = _render_attempt_list(views, request.query_params.multi_items())
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except AttemptInvestigationAccessDeniedError:
            return _empty(status.HTTP_403_FORBIDDEN)
        except InvalidAttemptInvestigationFilterError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return HTMLResponse(content=content, headers=_NO_STORE_HEADERS)

    @app.get("/staff/attempts/{attempt_id}", response_class=HTMLResponse)
    def attempt_detail(
        attempt_id: str,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> Response:
        try:
            with _database_session(session_factory) as database_session:
                principal = get_current_principal(
                    database_session, session_token=fm_staff_session
                )
                authorize_attempt_investigation(principal)
                try:
                    parsed_attempt_id = uuid.UUID(attempt_id)
                except ValueError:
                    return _empty(status.HTTP_404_NOT_FOUND)
                view = read_attempt_detail(
                    database_session,
                    principal=principal,
                    attempt_id=parsed_attempt_id,
                )
                content = _render_attempt_detail(view)
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except AttemptInvestigationAccessDeniedError:
            return _empty(status.HTTP_403_FORBIDDEN)
        except AttemptInvestigationNotFoundError:
            return _empty(status.HTTP_404_NOT_FOUND)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return HTMLResponse(content=content, headers=_NO_STORE_HEADERS)


def parse_attempt_filters(request: Request) -> AttemptInvestigationFilters:
    pairs = list(request.query_params.multi_items())
    names = [name for name, _value in pairs]
    if any(name not in _FILTER_NAMES for name in names) or len(names) != len(set(names)):
        raise InvalidAttemptInvestigationFilterError
    values = dict(pairs)
    try:
        attempt_id = _optional_uuid(values.get("attempt_id"))
        correlation_id = _optional_uuid(values.get("correlation_id"))
        created_at_from = _optional_utc(values.get("from"))
        created_at_to = _optional_utc(values.get("to"))
        state_value = values.get("state")
        if state_value is not None and state_value not in _STATES:
            raise ValueError
        processing_status = (
            None if state_value is None else state_value
        )
        return AttemptInvestigationFilters(
            attempt_id=attempt_id,
            correlation_id=correlation_id,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            processing_status=processing_status,  # type: ignore[arg-type]
        )
    except (TypeError, ValueError) as error:
        raise InvalidAttemptInvestigationFilterError from error


def _optional_uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    if not value:
        raise ValueError
    return uuid.UUID(value)


def _optional_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not value:
        raise ValueError
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError
    return parsed.astimezone(timezone.utc)


def _render_attempt_list(
    views: Sequence[AttemptInvestigationView],
    active_filters: Sequence[tuple[str, str]],
) -> str:
    rows = "".join(_render_list_row(view) for view in views)
    filters = dict(active_filters)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Attempts</title></head>
<body><main><h1>Attempts</h1>
<form method="get" action="/staff/attempts">
<label>Attempt ID <input name="attempt_id" value="{escape(filters.get('attempt_id', ''))}"></label>
<label>Correlation ID <input name="correlation_id" value="{escape(filters.get('correlation_id', ''))}"></label>
<label>From UTC <input name="from" value="{escape(filters.get('from', ''))}"></label>
<label>To UTC <input name="to" value="{escape(filters.get('to', ''))}"></label>
<label>State <input name="state" value="{escape(filters.get('state', ''))}"></label>
<button type="submit">Filter</button></form>
<table><thead><tr><th>Attempt</th><th>Correlation</th><th>Created</th><th>State</th><th>Outcome</th><th>Stages</th><th>Latency</th><th>Evidence</th><th>Issues</th></tr></thead>
<tbody>{rows}</tbody></table></main></body></html>"""


def _render_list_row(view: AttemptInvestigationView) -> str:
    core = view.core
    timeline = core.timeline
    stages = ", ".join(f"{name}={value}ms" for name, value in view.server_durations_ms()) or "unavailable"
    latency = (
        "unavailable"
        if timeline.qr_fully_visible_elapsed_ms is None
        else f"{timeline.qr_fully_visible_elapsed_ms}ms client-local"
    )
    return (
        f'<tr data-attempt-id="{core.attempt_id}">'
        f'<td><a href="/staff/attempts/{core.attempt_id}">{core.attempt_id}</a></td>'
        f"<td>{core.correlation_id}</td><td>{_iso(core.created_at)}</td>"
        f"<td>{escape(core.processing_status)}</td><td>{_text(core.domain_outcome)}</td>"
        f"<td>{escape(stages)}</td><td>{escape(latency)}</td>"
        f"<td>{view.evidence_availability}</td><td>{_tags(view.issue_tags)}</td></tr>"
    )


def _render_attempt_detail(view: AttemptInvestigationView) -> str:
    core = view.core
    timeline = core.timeline
    durations = "".join(
        f"<li>{escape(name)}: {value} ms</li>" for name, value in view.server_durations_ms()
    ) or "<li>unavailable</li>"
    developer = ""
    if view.developer_evidence is not None:
        evidence = view.developer_evidence
        manifest = (
            "unavailable"
            if evidence.ordinary_manifest is None
            else json.dumps(evidence.ordinary_manifest, sort_keys=True, ensure_ascii=True)
        )
        developer = (
            '<section id="developer-evidence"><h2>Developer evidence</h2>'
            f"<p>Schema version: {_text(evidence.schema_version)}</p>"
            f"<p>Completeness: {escape(evidence.completeness)}</p>"
            f"<p>Gap reason: {_text(evidence.gap_reason)}</p>"
            f"<pre>{escape(manifest)}</pre></section>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Attempt {core.attempt_id}</title></head>
<body><main><p><a href="/staff/attempts">Attempts</a></p><h1>Attempt detail</h1>
<dl><dt>Attempt ID</dt><dd>{core.attempt_id}</dd><dt>Correlation ID</dt><dd>{core.correlation_id}</dd>
<dt>Processing state</dt><dd>{escape(core.processing_status)}</dd><dt>Outcome</dt><dd>{_text(core.domain_outcome)}</dd>
<dt>Ready-series start</dt><dd>{_iso(timeline.reference_series_ready_at)}</dd>
<dt>Local detection completion</dt><dd>{timeline.local_detection_completed_ms} ms</dd>
<dt>Request start</dt><dd>{timeline.request_started_ms} ms</dd>
<dt>Response receipt</dt><dd>{_text(timeline.response_received_ms, suffix=' ms')}</dd>
<dt>Admission</dt><dd>{_iso(timeline.created_at)}</dd><dt>Slot decision</dt><dd>{_time(timeline.slot_decided_at)}</dd>
<dt>Search start</dt><dd>{_time(timeline.search_started_at)}</dd><dt>Search finish</dt><dd>{_time(timeline.search_finished_at)}</dd>
<dt>Display state</dt><dd>{escape(timeline.display_status)}</dd><dt>QR visible elapsed</dt><dd>{_text(timeline.qr_fully_visible_elapsed_ms, suffix=' ms')}</dd>
<dt>Evidence availability</dt><dd id="evidence-availability">{view.evidence_availability}</dd>
<dt>Issue tags</dt><dd>{_tags(view.issue_tags)}</dd></dl>
<section><h2>Server durations</h2><ul>{durations}</ul></section>{developer}</main></body></html>"""


def _tags(values: Sequence[str]) -> str:
    return escape(", ".join(values) if values else "none")


def _text(value: object | None, *, suffix: str = "") -> str:
    return "unavailable" if value is None else escape(f"{value}{suffix}")


def _time(value: datetime | None) -> str:
    return "unavailable" if value is None else _iso(value)


def _iso(value: datetime) -> str:
    return escape(value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))


def _empty(status_code: int) -> Response:
    return Response(status_code=status_code, headers=_NO_STORE_HEADERS)


def _database_session(session_factory: Callable[[], Session]) -> Session:
    return session_factory()


__all__ = [
    "InvalidAttemptInvestigationFilterError",
    "parse_attempt_filters",
    "register_attempt_investigation_routes",
]
