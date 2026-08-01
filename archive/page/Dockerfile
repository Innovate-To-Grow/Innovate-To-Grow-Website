# syntax=docker/dockerfile:1.7
# Archived I2G event pages — static file server + server-side Google Sheets
# proxy (see app.py). Mirrors the backend image's two-stage, non-root,
# pinned-base approach. This is the verified multi-platform Python 3.11.15
# slim-trixie OCI index used by the primary backend image.
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --require-hashes -r requirements.txt


FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system app \
 && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

# Installed Python packages from the builder stage.
COPY --from=builder /install /usr/local

# Application code: app.py, templates/, static/. The .dockerignore keeps
# .venv, .env, and tests out of the image.
COPY --chown=app:app . .

USER app

EXPOSE 5001

# Matches the load balancer health check path.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/healthz')" || exit 1

# waitress (production WSGI server) — same as `python app.py` without --debug.
CMD ["python", "app.py"]
