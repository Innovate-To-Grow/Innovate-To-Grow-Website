# syntax=docker/dockerfile:1.7
# Multi-platform OCI index for Python 3.11.15 slim-trixie, verified with:
# docker buildx imagetools inspect python:3.11-slim
# Keep the readable tag so Dependabot can propose a reviewed digest update.
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build-time dependencies. apt package versions pinned (DL3008) against the
# current python:3.11-slim (Debian trixie/deb13). Refresh with
# `apt-cache policy <pkg>` inside the base image when the upstream point
# release bumps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential=12.12 \
        libpq-dev=17.10-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

# Production images consume the fully resolved, hash-checked Python 3.11 lock.
# Development and CI tooling intentionally stays out of the runtime image.
COPY requirements/production.lock.txt requirements/production.lock.txt

# Resolved site-packages are staged under /install so the production stage can
# copy them without dragging the compiler toolchain.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --require-hashes \
        -r requirements/production.lock.txt


FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The runtime does not install packages. Removing build tooling also removes
# setuptools' vendored jaraco.context and wheel copies from the attack surface.
RUN python -m pip uninstall --yes setuptools wheel pip

# Runtime libs only. libpq5 is the runtime sibling of libpq-dev used by
# psycopg2. Version pinned (DL3008); refresh alongside libpq-dev above.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5=17.10-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

# Copy installed Python packages from the builder.
COPY --from=builder /install /usr/local

# Copy the application source.
COPY --chown=app:app . .

# Bake static assets into the image instead of running collectstatic at boot.
# config.settings.build uses SQLite and filesystem-backed
# ManifestStaticFilesStorage, so the exact image contains hashed assets and
# staticfiles.json without needing DB or S3 credentials.
RUN chmod +x entrypoint.sh \
 && mkdir -p data \
 && chown app:app data \
 && DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput \
 && test -s static/staticfiles.json

USER app

EXPOSE 8000

# Matches the ECS task-definition liveness probe so local `docker run` shows
# the same container health signal.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/livez/')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
