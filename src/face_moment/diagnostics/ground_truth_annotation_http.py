"""Thin HTML adapter for diagnostics-owned ground-truth annotations."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from html import escape
import uuid

from fastapi import Cookie, FastAPI, Header, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from face_moment.diagnostics.attempt_investigation import (
    GroundTruthAnnotationAccessDeniedError,
    authorize_ground_truth_annotations,
)
from face_moment.diagnostics.ground_truth_annotations import (
    GroundTruthAnnotationError,
    GroundTruthAnnotationNotFoundError,
    GroundTruthAnnotationProvider,
    GroundTruthAnnotationSnapshot,
)
from face_moment.platform.auth.sessions import (
    CsrfValidationError,
    InvalidSessionError,
    authenticate_unsafe_staff_request,
    get_current_principal,
)


_NO_STORE_HEADERS = {"Cache-Control": "no-store"}
_CREATE_FIELDS = frozenset(
    {"target_kind", "detection_occurrence_index", "participant_name", "outcome"}
)
_UPDATE_FIELDS = frozenset({"action", "participant_name", "outcome"})
_DELETE_FIELDS = frozenset({"action"})


class InvalidGroundTruthAnnotationFormError(ValueError):
    """The submitted HTML form is outside the exact mutation contract."""


def register_ground_truth_annotation_routes(
    app: FastAPI, *, session_factory: Callable[[], Session]
) -> None:
    @app.get(
        "/staff/attempts/{attempt_id}/annotations", response_class=HTMLResponse
    )
    def annotation_list(
        attempt_id: str,
        fm_staff_session: str | None = Cookie(default=None),
    ) -> Response:
        try:
            with _database_session(session_factory) as database_session:
                principal = get_current_principal(
                    database_session, session_token=fm_staff_session
                )
                authorize_ground_truth_annotations(principal)
                parsed_attempt_id = _parse_uuid(attempt_id)
                annotations = GroundTruthAnnotationProvider(database_session).list(
                    attempt_id=parsed_attempt_id
                )
                content = _render_annotation_page(parsed_attempt_id, annotations)
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except GroundTruthAnnotationAccessDeniedError:
            return _empty(status.HTTP_403_FORBIDDEN)
        except InvalidGroundTruthAnnotationFormError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except GroundTruthAnnotationNotFoundError:
            return _empty(status.HTTP_404_NOT_FOUND)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return HTMLResponse(content=content, headers=_NO_STORE_HEADERS)

    @app.post("/staff/attempts/{attempt_id}/annotations")
    async def annotation_create(
        request: Request,
        attempt_id: str,
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
                authorize_ground_truth_annotations(principal)
                form_pairs = list((await request.form()).multi_items())
                parsed_attempt_id = _parse_uuid(attempt_id)
                values = _parse_create_form(form_pairs)
                GroundTruthAnnotationProvider(database_session).create(
                    attempt_id=parsed_attempt_id,
                    target_kind=values["target_kind"],
                    detection_occurrence_index=_parse_occurrence_index(
                        values["detection_occurrence_index"]
                    ),
                    participant_name=values["participant_name"],
                    outcome=values["outcome"],
                )
                database_session.commit()
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except (CsrfValidationError, GroundTruthAnnotationAccessDeniedError):
            return _empty(status.HTTP_403_FORBIDDEN)
        except InvalidGroundTruthAnnotationFormError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except GroundTruthAnnotationNotFoundError:
            return _empty(status.HTTP_404_NOT_FOUND)
        except GroundTruthAnnotationError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return _redirect_to_annotations(parsed_attempt_id)

    @app.post("/staff/attempts/{attempt_id}/annotations/{annotation_id}")
    async def annotation_update_or_delete(
        request: Request,
        attempt_id: str,
        annotation_id: str,
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
                authorize_ground_truth_annotations(principal)
                form_pairs = list((await request.form()).multi_items())
                parsed_attempt_id = _parse_uuid(attempt_id)
                parsed_annotation_id = _parse_uuid(annotation_id)
                action = _parse_action(form_pairs)
                provider = GroundTruthAnnotationProvider(database_session)
                if action == "update":
                    values = _exact_form(form_pairs, _UPDATE_FIELDS)
                    provider.correct(
                        attempt_id=parsed_attempt_id,
                        annotation_id=parsed_annotation_id,
                        participant_name=values["participant_name"],
                        outcome=values["outcome"],
                    )
                else:
                    _exact_form(form_pairs, _DELETE_FIELDS)
                    provider.remove(
                        attempt_id=parsed_attempt_id,
                        annotation_id=parsed_annotation_id,
                    )
                database_session.commit()
        except InvalidSessionError:
            return _empty(status.HTTP_401_UNAUTHORIZED)
        except (CsrfValidationError, GroundTruthAnnotationAccessDeniedError):
            return _empty(status.HTTP_403_FORBIDDEN)
        except InvalidGroundTruthAnnotationFormError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except GroundTruthAnnotationNotFoundError:
            return _empty(status.HTTP_404_NOT_FOUND)
        except GroundTruthAnnotationError:
            return _empty(status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception:
            return _empty(status.HTTP_500_INTERNAL_SERVER_ERROR)
        return _redirect_to_annotations(parsed_attempt_id)


def _parse_create_form(pairs: Sequence[tuple[str, object]]) -> Mapping[str, str]:
    return _exact_form(pairs, _CREATE_FIELDS)


def _parse_action(pairs: Sequence[tuple[str, object]]) -> str:
    actions = [value for name, value in pairs if name == "action"]
    if len(actions) != 1 or actions[0] not in {"update", "delete"}:
        raise InvalidGroundTruthAnnotationFormError
    return str(actions[0])


def _exact_form(
    pairs: Sequence[tuple[str, object]], allowed: frozenset[str]
) -> Mapping[str, str]:
    names = [name for name, _value in pairs]
    if set(names) != allowed or len(names) != len(set(names)):
        raise InvalidGroundTruthAnnotationFormError
    values: dict[str, str] = {}
    for name, value in pairs:
        if not isinstance(value, str):
            raise InvalidGroundTruthAnnotationFormError
        values[name] = value
    return values


def _parse_occurrence_index(value: str) -> int | None:
    if value == "":
        return None
    try:
        return int(value)
    except ValueError as error:
        raise InvalidGroundTruthAnnotationFormError from error


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise InvalidGroundTruthAnnotationFormError from error


def _render_annotation_page(
    attempt_id: uuid.UUID, annotations: Sequence[GroundTruthAnnotationSnapshot]
) -> str:
    annotation_rows = (
        "".join(_render_annotation_row(annotation) for annotation in annotations)
        if annotations
        else "<p>No annotations</p>"
    )
    action = f"/staff/attempts/{attempt_id}/annotations"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Attempt annotations</title></head>
<body><main><p><a href="/staff/attempts/{attempt_id}">Attempt detail</a></p><h1>Attempt annotations</h1>
<p>Attempt ID: <span id="annotation-attempt-id">{attempt_id}</span></p>
<section><h2>Current annotations</h2>{annotation_rows}</section>
<section><h2>Add detection annotation</h2><form data-protected method="post" action="{action}">
<input type="hidden" name="target_kind" value="detection">
<label>Detection occurrence <input name="detection_occurrence_index" type="number" min="0" required></label>
<label>Participant name <input name="participant_name" maxlength="200" required></label>
<label>Outcome <select name="outcome"><option value="correct">correct</option><option value="false">false</option></select></label>
<button type="submit">Create detection annotation</button></form></section>
<section><h2>Add missed person</h2><form data-protected method="post" action="{action}">
<input type="hidden" name="target_kind" value="person"><input type="hidden" name="detection_occurrence_index" value="">
<label>Participant name <input name="participant_name" maxlength="200" required></label><input type="hidden" name="outcome" value="missed">
<button type="submit">Create missed annotation</button></form></section>
<script>{_FORM_SCRIPT}</script></main></body></html>"""


def _render_annotation_row(annotation: GroundTruthAnnotationSnapshot) -> str:
    action = (
        f"/staff/attempts/{annotation.attempt_id}/annotations/"
        f"{annotation.annotation_id}"
    )
    occurrence = (
        "person" if annotation.detection_occurrence_index is None else str(annotation.detection_occurrence_index)
    )
    outcomes = (
        '<option value="correct">correct</option><option value="false">false</option>'
        if annotation.target_kind == "detection"
        else '<option value="missed">missed</option>'
    )
    selected_outcomes = outcomes.replace(
        f'value="{annotation.outcome}"', f'value="{annotation.outcome}" selected'
    )
    return (
        f'<article data-annotation-id="{annotation.annotation_id}">'
        f"<p>Target: {escape(annotation.target_kind)} {escape(occurrence)}</p>"
        f'<form data-protected method="post" action="{action}"><input type="hidden" name="action" value="update">'
        f'<label>Participant name <input name="participant_name" maxlength="200" value="{escape(annotation.participant_name)}" required></label>'
        f'<label>Outcome <select name="outcome">{selected_outcomes}</select></label><button type="submit">Update annotation</button></form>'
        f'<form data-protected method="post" action="{action}"><input type="hidden" name="action" value="delete"><button type="submit">Delete annotation</button></form></article>'
    )


_FORM_SCRIPT = r"""
const csrfToken = () => document.cookie.split("; ")
  .find((item) => item.startsWith("fm_staff_csrf="))?.slice("fm_staff_csrf=".length) ?? "";
for (const form of document.querySelectorAll("form[data-protected]")) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form, event.submitter),
      headers: {"X-CSRF-Token": csrfToken()},
      redirect: "follow",
    });
    if (response.redirected) window.location.assign(response.url);
  });
}
"""


def _redirect_to_annotations(attempt_id: uuid.UUID) -> RedirectResponse:
    return RedirectResponse(
        url=f"/staff/attempts/{attempt_id}/annotations",
        status_code=status.HTTP_303_SEE_OTHER,
        headers=_NO_STORE_HEADERS,
    )


def _empty(status_code: int) -> Response:
    return Response(status_code=status_code, headers=_NO_STORE_HEADERS)


def _database_session(session_factory: Callable[[], Session]) -> Session:
    return session_factory()


__all__ = [
    "InvalidGroundTruthAnnotationFormError",
    "register_ground_truth_annotation_routes",
]
