# syntax=docker/dockerfile:1.7
# Archived I2G event pages — static file server + server-side Google Sheets
# proxy (see app.py). Mirrors the backend image's two-stage, non-root,
# pinned-base approach.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt .
RUN pip install "pip==26.1" \
 && pip install --prefix=/install -r requirements.txt


FROM python:3.11-slim AS production

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
