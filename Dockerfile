FROM python:3.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN sed -i 's|URIs: http://deb.debian.org/|URIs: https://deb.debian.org/|' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install --yes --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements-runtime.lock.txt ./
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    unset PIP_NO_CACHE_DIR \
    && python -m pip wheel --no-deps --wheel-dir /wheels -r requirements-runtime.lock.txt

FROM builder AS app_builder

COPY pyproject.toml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    unset PIP_NO_CACHE_DIR \
    && python -m pip wheel --no-deps --wheel-dir /app-wheels .

FROM python:3.11-slim-bookworm AS runtime

ENV TZ=Asia/Novosibirsk \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FACE_MOMENT_CLIENT_ROOT=/app/client \
    PIP_NO_CACHE_DIR=1

RUN sed -i 's|URIs: http://deb.debian.org/|URIs: https://deb.debian.org/|' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install --yes --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-index --no-deps /wheels/*.whl \
    && rm -rf /wheels
COPY --from=app_builder /app-wheels /app-wheels
RUN python -m pip install --no-index --no-deps /app-wheels/*.whl \
    && rm -rf /app-wheels

COPY --chown=app:app pyproject.toml alembic.ini ./
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app scripts/runtime-storage-probe.py ./scripts/runtime-storage-probe.py
COPY --chown=app:app src ./src
COPY --chown=app:app tests ./tests
COPY --chown=app:app client ./client
COPY --chown=app:app deploy/Caddyfile ./deploy/Caddyfile

USER app
CMD ["face-moment-backend"]
