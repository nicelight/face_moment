"""Thin HTTP adapters for diagnostics-owned staff investigation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from html import escape
import json
import re
import uuid

from fastapi import Cookie, FastAPI, Request, Response, status
from fastapi.responses import HTMLResponse
from face_moment.platform.staff_presentation import staff_document
from sqlalchemy.orm import Session

from face_moment.diagnostics.attempt_investigation import (
    AttemptInvestigationAccessDeniedError,
    AttemptInvestigationNotFoundError,
    AttemptInvestigationView,
    authorize_attempt_investigation,
    read_attempt_detail,
    read_attempts,
)
from face_moment.diagnostics.server_event_search import (
    ServerEventSearchAccessDeniedError,
    authorize_server_event_search,
    search_server_events,
)
from face_moment.diagnostics.server_events import (
    EVENT_CATALOG,
    ServerEventCode,
    ServerEventProjection,
    ServerEventSearchFilters,
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
_SERVER_EVENT_FILTER_NAMES = frozenset(
    {
        "from",
        "to",
        "severity",
        "component",
        "event_code",
        "attempt_id",
        "correlation_id",
    }
)
_SERVER_EVENT_SEVERITIES = frozenset(
    definition.severity for definition in EVENT_CATALOG.values()
)
_SERVER_EVENT_COMPONENTS = frozenset(
    definition.component for definition in EVENT_CATALOG.values()
)
_SERVER_EVENT_MAXIMUM_RANGE = timedelta(days=7)
_SERVER_EVENT_DEFAULT_RANGE = timedelta(hours=24)
_SERVER_EVENT_RFC3339_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:[Zz]|\+00:00)"
)


class InvalidAttemptInvestigationFilterError(ValueError):
    """The list query is outside the exact bounded filter contract."""


class InvalidServerEventFilterError(ValueError):
    """The event query is outside the exact bounded filter contract."""


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
        return HTMLResponse(content=staff_document(content, "attempts"), headers=_NO_STORE_HEADERS)

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
        return HTMLResponse(content=staff_document(content, "attempt-detail"), headers=_NO_STORE_HEADERS)


def register_server_event_search_routes(
    app: FastAPI,
    *,
    session_factory: Callable[[], Session],
    utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> None:
    @app.get("/staff/server-events", response_class=HTMLResponse)
    def server_event_list(
        request: Request,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> Response:
        try:
            with _database_session(session_factory) as database_session:
                principal = get_current_principal(
                    database_session, session_token=fm_staff_session
                )
                authorize_server_event_search(principal)
                filters = parse_server_event_filters(request, now=utc_now())
                events = search_server_events(
                    database_session,
                    principal=principal,
                    filters=filters,
                )
                content = _render_server_event_page(
                    events, request.query_params.multi_items()
                )
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except ServerEventSearchAccessDeniedError:
            return _empty(status.HTTP_403_FORBIDDEN)
        except InvalidServerEventFilterError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return HTMLResponse(content=staff_document(content, "server-events"), headers=_NO_STORE_HEADERS)


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


def parse_server_event_filters(
    request: Request, *, now: datetime
) -> ServerEventSearchFilters:
    pairs = list(request.query_params.multi_items())
    names = [name for name, _value in pairs]
    if any(name not in _SERVER_EVENT_FILTER_NAMES for name in names) or len(
        names
    ) != len(set(names)):
        raise InvalidServerEventFilterError
    values = dict(pairs)
    try:
        occurred_at_from = _optional_server_event_utc(values.get("from"))
        occurred_at_to = _optional_server_event_utc(values.get("to"))
        if (occurred_at_from is None) != (occurred_at_to is None):
            raise ValueError
        if occurred_at_from is None:
            occurred_at_to = _utc(now)
            occurred_at_from = occurred_at_to - _SERVER_EVENT_DEFAULT_RANGE
        assert occurred_at_to is not None
        if (
            occurred_at_to <= occurred_at_from
            or occurred_at_to - occurred_at_from > _SERVER_EVENT_MAXIMUM_RANGE
        ):
            raise ValueError

        severity_value = values.get("severity")
        if (
            severity_value is not None
            and severity_value not in _SERVER_EVENT_SEVERITIES
        ):
            raise ValueError
        component_value = values.get("component")
        if (
            component_value is not None
            and component_value not in _SERVER_EVENT_COMPONENTS
        ):
            raise ValueError
        event_code_value = values.get("event_code")
        event_code = (
            None if event_code_value is None else ServerEventCode(event_code_value)
        )
        return ServerEventSearchFilters(
            occurred_at_from=occurred_at_from,
            occurred_at_to=occurred_at_to,
            severity=severity_value,  # type: ignore[arg-type]
            component=component_value,  # type: ignore[arg-type]
            event_code=event_code,
            attempt_id=_optional_uuid(values.get("attempt_id")),
            correlation_id=_optional_uuid(values.get("correlation_id")),
        )
    except (TypeError, ValueError) as error:
        raise InvalidServerEventFilterError from error


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


def _optional_server_event_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    if _SERVER_EVENT_RFC3339_UTC.fullmatch(value) is None:
        raise ValueError
    normalized = f"{value[:-1]}+00:00" if value[-1] in {"Z", "z"} else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.utcoffset() != timedelta(0):
        raise ValueError
    return parsed.astimezone(timezone.utc)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError
    return value.astimezone(timezone.utc)


def _render_server_event_page(
    events: Sequence[ServerEventProjection],
    active_filters: Sequence[tuple[str, str]],
) -> str:
    rows = "".join(_render_server_event_row(event) for event in events)
    filters = dict(active_filters)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Server events</title></head>
<body><main><h1>Server events</h1>
<form id="server-event-search" method="get" action="/staff/server-events">
<label>From UTC <input name="from" value="{escape(filters.get('from', ''))}"></label>
<label>To UTC <input name="to" value="{escape(filters.get('to', ''))}"></label>
<label>Severity <input name="severity" value="{escape(filters.get('severity', ''))}"></label>
<label>Component <input name="component" value="{escape(filters.get('component', ''))}"></label>
<label>Event code <input name="event_code" value="{escape(filters.get('event_code', ''))}"></label>
<label>Attempt ID <input name="attempt_id" value="{escape(filters.get('attempt_id', ''))}"></label>
<label>Correlation ID <input name="correlation_id" value="{escape(filters.get('correlation_id', ''))}"></label>
<button type="submit">Filter</button></form>
<script>
const form = document.getElementById("server-event-search");
form.addEventListener("submit", () => {{
  for (const control of form.querySelectorAll("[name]")) {{
    if (control.value === "") control.disabled = true;
  }}
}});
</script>
<table><thead><tr><th>Event time</th><th>Severity</th><th>Component</th><th>Event code</th><th>Release ID</th><th>Attempt ID</th><th>Correlation ID</th></tr></thead>
<tbody>{rows}</tbody></table></main></body></html>"""


def _render_server_event_row(event: ServerEventProjection) -> str:
    if (event.attempt_id is None) != (event.correlation_id is None):
        raise ValueError("server-event identities must be paired or absent")
    attempt = ""
    correlation = ""
    if event.attempt_id is not None and event.correlation_id is not None:
        attempt = (
            f'<a href="/staff/attempts/{event.attempt_id}">{event.attempt_id}</a>'
        )
        correlation = str(event.correlation_id)
    return (
        "<tr>"
        f"<td>{_iso(event.occurred_at)}</td><td>{escape(event.severity)}</td>"
        f"<td>{escape(event.component)}</td><td>{escape(event.event_code.value)}</td>"
        f"<td>{escape(event.release_id)}</td><td>{attempt}</td>"
        f"<td>{correlation}</td></tr>"
    )


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
            else json.dumps(evidence.ordinary_manifest, sort_keys=True, ensure_ascii=False, indent=2)
        )
        developer = (
            '<section id="developer-evidence"><h2>Developer evidence</h2>'
            f"<p>Schema version: {_text(evidence.schema_version)}</p>"
            f"<p>Completeness: {escape(evidence.completeness)}</p>"
            f"<p>Gap reason: {_text(evidence.gap_reason)}</p>"
            f"{_render_search_evidence(evidence.ordinary_manifest)}"
            f"<details><summary>Исходные диагностические данные (JSON)</summary><pre>{escape(manifest)}</pre></details>"
            f'<p><a href="/staff/attempts/{core.attempt_id}/annotations">Annotations</a></p></section>'
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


def _render_search_evidence(manifest: dict[str, object] | None) -> str:
    """Explain existing developer evidence without inferring missing search scores."""
    if manifest is None:
        return ""
    serving = manifest.get("serving")
    client = manifest.get("client")
    fields: list[tuple[str, object]] = []
    if isinstance(serving, dict):
        fields.extend((label, serving.get(key)) for label, key in (
            ("Дата поиска", "visit_date"),
            ("Модель", "pipeline_code"),
            ("Версия обработки", "pipeline_revision_id"),
            ("Версия настроек", "settings_revision"),
            ("Порог сходства", "threshold"),
            ("Настройки качества", "quality_settings"),
        ))
    if isinstance(client, dict):
        fields.append(("Передано предложений лиц", client.get("proposal_count")))
    parameters = "".join(
        f"<dt>{escape(label)}</dt><dd>{_text(value)}</dd>" for label, value in fields
    )
    detections = manifest.get("detections")
    rows = ""
    best_scores: list[float] = []
    if isinstance(detections, list):
        for detection in detections:
            if not isinstance(detection, dict):
                continue
            matches = detection.get("matches")
            observations = (
                [match for match in matches if isinstance(match, dict)]
                if isinstance(matches, list) else []
            )
            best = detection.get("best_cosine_similarity")
            best_label = "не сохранено"
            if isinstance(best, (int, float)) and not isinstance(best, bool):
                best_scores.append(float(best))
                best_label = format(best, ".4f")
            elif "best_cosine_similarity" in detection:
                best_label = "нет оценки"
            gate = detection.get("quality_gate_passed")
            gate_label = "пройден" if gate is True else "не пройден" if gate is False else "нет данных"
            rows += (
                "<tr>"
                f"<td>{_text(detection.get('rank'))}</td>"
                f"<td>{_text(detection.get('occurrence_index'))}</td>"
                f"<td>{_text(detection.get('reference_quality_score'))}</td>"
                f"<td>{gate_label}</td>"
                f"<td>{_text(detection.get('rejection_reason'))}</td>"
                f"<td>{_text(detection.get('eligible_photo_count'))}</td>"
                f"<td>{len(observations) if isinstance(matches, list) else 'нет данных'}</td>"
                f"<td>{best_label}</td></tr>"
            )
    table = (
        "<table><thead><tr><th>Ранг</th><th>Индекс лица (с 0)</th><th>Оценка качества</th>"
        "<th>Фильтр качества</th><th>Причина отклонения</th><th>Фотографий в поиске</th><th>Совпадений ≥ порога</th>"
        f"<th>Лучшее сходство до порога</th></tr></thead><tbody>{rows}</tbody></table>"
        if rows else "<p>Наблюдения поиска не сохранены; это не означает, что камера не нашла лиц.</p>"
    )
    return (
        '<section id="search-evidence-summary"><h3>Диагностика поиска</h3>'
        '<p>Лучшее сходство среди сохранённых поисковых наблюдений: '
        f'<strong id="best-cosine-similarity">{format(max(best_scores), ".4f") if best_scores else "нет данных"}</strong></p>'
        f"<dl>{parameters}</dl>{table}"
        "<p>Оценка качества лица не является оценкой сходства с фотографией. "
        "Лучшее сходство — cosine similarity, а не вероятность узнавания. "
        "Оно измеряется до отсечения по порогу; список совпадений содержит только прошедшие порог фотографии. "
        "«Нет оценки» означает, что поиск не выполнялся или в его области не было подходящих фотографий. "
        "В старых попытках эта оценка не сохранена; при превышении времени результаты поиска могут быть недоступны.</p></section>"
    )


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
    "InvalidServerEventFilterError",
    "parse_attempt_filters",
    "parse_server_event_filters",
    "register_attempt_investigation_routes",
    "register_server_event_search_routes",
]
