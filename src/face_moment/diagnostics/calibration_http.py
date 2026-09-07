"""Thin same-origin HTML adapter for diagnostics-owned Calibration runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from html import escape
import json
import uuid

from fastapi import Cookie, FastAPI, Header, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from face_moment.diagnostics.calibration_runs import (
    CalibrationAccessDeniedError,
    CalibrationRun,
    CalibrationRunError,
    CalibrationRunNotFoundError,
    CalibrationRunService,
    CalibrationSelectionConflictError,
    CalibrationSelectionNotFoundError,
    StoredServingRecommendation,
    authorize_calibration,
)
from face_moment.platform.auth.sessions import (
    CsrfValidationError,
    InvalidSessionError,
    authenticate_unsafe_staff_request,
    get_current_principal,
)
from face_moment.serving_control.realtime_context import (
    CalibrationRecommendationConflictError,
)

_NO_STORE_HEADERS = {"Cache-Control": "no-store"}
_CREATE_FIELDS = frozenset(
    {"photo_ids", "attempt_ids", "sface_revision_id", "buffalo_revision_id"}
)
_APPLY_FIELDS = frozenset({"action", "recommendation_key", "confirmation"})


class InvalidCalibrationFormError(ValueError):
    """The submitted form is outside the exact Calibration route contract."""


def register_calibration_routes(
    app: FastAPI, *, session_factory: Callable[[], Session]
) -> None:
    @app.get("/staff/calibrations", response_class=HTMLResponse)
    def calibration_list(
        fm_staff_session: str | None = Cookie(default=None),
    ) -> Response:
        try:
            with _database_session(session_factory) as database_session:
                principal = get_current_principal(
                    database_session, session_token=fm_staff_session
                )
                authorize_calibration(principal)
                runs = CalibrationRunService(database_session).list_recent()
                content = _render_list(runs)
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except CalibrationAccessDeniedError:
            return _empty(status.HTTP_403_FORBIDDEN)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return HTMLResponse(content=content, headers=_NO_STORE_HEADERS)

    @app.post("/staff/calibrations")
    async def calibration_create(
        request: Request,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> Response:
        try:
            with _database_session(session_factory) as database_session:
                principal = authenticate_unsafe_staff_request(
                    database_session,
                    session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf,
                    csrf_header_token=x_csrf_token,
                )
                authorize_calibration(principal)
                values = _exact_form(
                    list((await request.form()).multi_items()), _CREATE_FIELDS
                )
                run = CalibrationRunService(database_session).request_from_selection(
                    requested_by_staff_id=principal.staff_user_id,
                    photo_ids=_uuid_list(values["photo_ids"]),
                    selected_attempt_ids=_uuid_list(values["attempt_ids"]),
                    sface_revision_id=_uuid(values["sface_revision_id"]),
                    buffalo_revision_id=_uuid(values["buffalo_revision_id"]),
                )
                run_id = run.id
                database_session.commit()
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except (CsrfValidationError, CalibrationAccessDeniedError):
            return _empty(status.HTTP_403_FORBIDDEN)
        except InvalidCalibrationFormError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except (CalibrationRunNotFoundError, CalibrationSelectionNotFoundError):
            return _empty(status.HTTP_404_NOT_FOUND)
        except (CalibrationRunError, CalibrationSelectionConflictError):
            return _empty(status.HTTP_409_CONFLICT)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return _redirect(run_id)

    @app.get(
        "/staff/calibrations/{calibration_id}", response_class=HTMLResponse
    )
    def calibration_detail(
        calibration_id: str,
        applied_revision: str | None = None,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> Response:
        try:
            with _database_session(session_factory) as database_session:
                principal = get_current_principal(
                    database_session, session_token=fm_staff_session
                )
                authorize_calibration(principal)
                service = CalibrationRunService(database_session)
                run = service.require(_uuid(calibration_id))
                recommendations = service.serving_recommendations(run)
                content = _render_detail(
                    run,
                    recommendations,
                    applied=service.is_applied_result(
                        run=run,
                        settings_revision=_positive_int(applied_revision),
                    ),
                )
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except CalibrationAccessDeniedError:
            return _empty(status.HTTP_403_FORBIDDEN)
        except InvalidCalibrationFormError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except CalibrationRunNotFoundError:
            return _empty(status.HTTP_404_NOT_FOUND)
        except CalibrationSelectionConflictError:
            return _empty(status.HTTP_409_CONFLICT)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return HTMLResponse(content=content, headers=_NO_STORE_HEADERS)

    @app.post("/staff/calibrations/{calibration_id}")
    async def calibration_apply(
        request: Request,
        calibration_id: str,
        fm_staff_session: str | None = Cookie(default=None),
        fm_staff_csrf: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> Response:
        try:
            with _database_session(session_factory) as database_session:
                principal = authenticate_unsafe_staff_request(
                    database_session,
                    session_token=fm_staff_session,
                    csrf_cookie_token=fm_staff_csrf,
                    csrf_header_token=x_csrf_token,
                )
                authorize_calibration(principal)
                values = _exact_form(
                    list((await request.form()).multi_items()), _APPLY_FIELDS
                )
                if values["action"] != "apply" or values["confirmation"] != "apply":
                    raise InvalidCalibrationFormError
                run_id = _uuid(calibration_id)
                applied_revision = CalibrationRunService(
                    database_session
                ).apply_stored_recommendation(
                    run_id=run_id,
                    recommendation_key=values["recommendation_key"],
                )
                database_session.commit()
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except (CsrfValidationError, CalibrationAccessDeniedError):
            return _empty(status.HTTP_403_FORBIDDEN)
        except InvalidCalibrationFormError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except (CalibrationRunNotFoundError, CalibrationSelectionNotFoundError):
            return _empty(status.HTTP_404_NOT_FOUND)
        except (
            CalibrationRunError,
            CalibrationSelectionConflictError,
            CalibrationRecommendationConflictError,
        ):
            return _empty(status.HTTP_409_CONFLICT)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return _redirect(run_id, applied_revision=applied_revision)


def _exact_form(
    pairs: Sequence[tuple[str, object]], allowed: frozenset[str]
) -> Mapping[str, str]:
    names = [name for name, _value in pairs]
    if set(names) != allowed or len(names) != len(set(names)):
        raise InvalidCalibrationFormError
    values: dict[str, str] = {}
    for name, value in pairs:
        if not isinstance(value, str):
            raise InvalidCalibrationFormError
        values[name] = value
    return values


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (AttributeError, ValueError) as error:
        raise InvalidCalibrationFormError from error


def _uuid_list(value: str) -> tuple[uuid.UUID, ...]:
    parts = tuple(part.strip() for part in value.split(","))
    if not parts or any(not part for part in parts):
        raise InvalidCalibrationFormError
    return tuple(_uuid(part) for part in parts)


def _positive_int(value: str | None) -> int | None:
    if value is None or not value.isdigit():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _render_list(runs: Sequence[CalibrationRun]) -> str:
    rows = (
        "".join(
            "<tr>"
            f'<td><a href="/staff/calibrations/{run.id}">{run.id}</a></td>'
            f'<td data-field="status">{escape(run.status)}</td>'
            f'<td>{escape(run.created_at.isoformat())}</td>'
            "</tr>"
            for run in runs
        )
        or '<tr><td colspan="3">No Calibration runs</td></tr>'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Calibration runs</title></head>
<body><main><h1>Calibration runs</h1>
<table><thead><tr><th>Run</th><th>Status</th><th>Created</th></tr></thead><tbody>{rows}</tbody></table>
<section><h2>Create Calibration run</h2><form data-protected method="post" action="/staff/calibrations">
<label>Photo UUIDs <input name="photo_ids" autocomplete="off" required></label>
<label>Attempt UUIDs <input name="attempt_ids" autocomplete="off" required></label>
<label>SFace revision UUID <input name="sface_revision_id" autocomplete="off" required></label>
<label>Buffalo M revision UUID <input name="buffalo_revision_id" autocomplete="off" required></label>
<button type="submit">Create Calibration run</button></form><output data-form-status role="status"></output></section>
<script>{_FORM_SCRIPT}</script></main></body></html>"""


def _render_detail(
    run: CalibrationRun,
    recommendations: Sequence[StoredServingRecommendation],
    *,
    applied: bool,
) -> str:
    attempts = _attempt_ids(run.dataset_snapshot)
    selection = _render_selection(run.dataset_snapshot)
    drill_down = (
        "".join(
            f'<li><a href="/staff/attempts/{attempt_id}">{attempt_id}</a></li>'
            for attempt_id in attempts
        )
        or "<li>No applicable Attempts</li>"
    )
    options = "".join(
        f'<option value="{escape(item.key)}">{escape(item.key)}</option>'
        for item in recommendations
    )
    disabled = " disabled" if not recommendations else ""
    result = "No completed result" if run.result_bundle is None else escape(
        json.dumps(run.result_bundle, sort_keys=True, indent=2, ensure_ascii=True)
    )
    applied_notice = (
        '<p id="apply-result" role="status">Stored recommendation applied.</p>'
        if applied
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Calibration {run.id}</title></head>
<body><main><p><a href="/staff/calibrations">Calibration runs</a></p><h1>Calibration detail</h1>{applied_notice}
<dl><dt>Run ID</dt><dd id="calibration-id">{run.id}</dd><dt>Status</dt><dd id="calibration-status">{escape(run.status)}</dd><dt>Input snapshot SHA-256 (data + evaluation settings)</dt><dd>{escape(run.dataset_sha256)}</dd></dl>
{selection}
<section><h2>Stored results</h2><pre id="calibration-results">{result}</pre></section>
<section><h2>Attempt drill-down</h2><ul>{drill_down}</ul></section>
<section><h2>Manual serving apply</h2><p>Type <code>apply</code> to confirm the selected stored recommendation.</p>
<form data-protected method="post" action="/staff/calibrations/{run.id}"{disabled}>
<input type="hidden" name="action" value="apply"><label>Stored recommendation <select name="recommendation_key">{options}</select></label>
<label>Confirmation <input name="confirmation" autocomplete="off" required></label><button type="submit">Apply stored recommendation</button></form>
<output data-form-status role="status"></output></section><script>{_FORM_SCRIPT}</script></main></body></html>"""


def _attempt_ids(snapshot: Mapping[str, object]) -> tuple[str, ...]:
    values = snapshot.get("attempts")
    if not isinstance(values, list):
        return ()
    result: list[str] = []
    for value in values:
        if isinstance(value, Mapping) and isinstance(value.get("attempt_id"), str):
            result.append(value["attempt_id"])
    return tuple(result)


def _render_selection(snapshot: Mapping[str, object]) -> str:
    selected = _selected_attempt_ids(snapshot)
    applicable = _attempt_ids(snapshot)
    exclusions = _selection_exclusions(snapshot)
    if selected is None:
        return f"""<section><h2>Attempt selection</h2><dl>
<dt>Selected Attempt count</dt><dd id="calibration-selected-attempt-count">Unavailable in legacy snapshot</dd>
<dt>Applicable annotated Attempt count</dt><dd id="calibration-applicable-attempt-count">{len(applicable)}</dd>
<dt>Excluded Attempt count</dt><dd id="calibration-excluded-attempt-count">Unavailable in legacy snapshot</dd>
</dl><p>Selected Attempt IDs unavailable in legacy snapshot.</p></section>"""
    selected_rows = "".join(
        f'<li><a href="/staff/attempts/{escape(attempt_id)}">{escape(attempt_id)}</a></li>'
        for attempt_id in selected
    ) or "<li>No selected Attempts</li>"
    exclusion_rows = "".join(
        f'<li><a href="/staff/attempts/{escape(attempt_id)}">{escape(attempt_id)}</a>: {escape(reason)}</li>'
        for attempt_id, reason in exclusions
    ) or "<li>No selection exclusions</li>"
    return f"""<section><h2>Attempt selection</h2><dl>
<dt>Selected Attempt count</dt><dd id="calibration-selected-attempt-count">{len(selected)}</dd>
<dt>Applicable annotated Attempt count</dt><dd id="calibration-applicable-attempt-count">{len(applicable)}</dd>
<dt>Excluded Attempt count</dt><dd id="calibration-excluded-attempt-count">{len(exclusions)}</dd>
</dl><p>Selected Attempt IDs</p><ul id="calibration-selected-attempts">{selected_rows}</ul>
<p>Selection exclusions</p><ul id="calibration-selection-exclusions">{exclusion_rows}</ul></section>"""


def _selected_attempt_ids(snapshot: Mapping[str, object]) -> tuple[str, ...] | None:
    values = snapshot.get("selected_attempt_ids")
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        return None
    return tuple(values)


def _selection_exclusions(snapshot: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    values = snapshot.get("selection_exclusions")
    if not isinstance(values, list):
        return ()
    result: list[tuple[str, str]] = []
    for value in values:
        if (
            isinstance(value, Mapping)
            and isinstance(value.get("attempt_id"), str)
            and isinstance(value.get("reason"), str)
        ):
            result.append((value["attempt_id"], value["reason"]))
    return tuple(result)


_FORM_SCRIPT = r"""
const csrfToken = () => document.cookie.split("; ")
  .find((item) => item.startsWith("fm_staff_csrf="))?.slice("fm_staff_csrf=".length) ?? "";
for (const form of document.querySelectorAll("form[data-protected]")) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const statusOutput = document.querySelector("[data-form-status]");
    const response = await fetch(form.getAttribute("action"), {
      method: "POST",
      body: new FormData(form),
      headers: {"X-CSRF-Token": csrfToken()},
      redirect: "follow",
    });
    if (response.redirected) { window.location.assign(response.url); return; }
    statusOutput.value = `Request failed (${response.status})`;
  });
}
"""


def _redirect(
    run_id: uuid.UUID, *, applied_revision: int | None = None
) -> RedirectResponse:
    suffix = (
        f"?applied_revision={applied_revision}"
        if applied_revision is not None
        else ""
    )
    return RedirectResponse(
        url=f"/staff/calibrations/{run_id}{suffix}",
        status_code=status.HTTP_303_SEE_OTHER,
        headers=_NO_STORE_HEADERS,
    )


def _empty(status_code: int) -> Response:
    return Response(status_code=status_code, headers=_NO_STORE_HEADERS)


def _database_session(session_factory: Callable[[], Session]) -> Session:
    return session_factory()


__all__ = ["InvalidCalibrationFormError", "register_calibration_routes"]
