# syntax=docker/dockerfile:1.7
# Pin the base image by major-minor and (ideally) digest. Production images
# should use a specific @sha256 digest once CI pins are in place; until then
# the tag is updated through Dependabot/Renovate for visibility.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build-time dependencies. apt package versions pinned (DL3008) against the
# current python:3.11-slim (Debian trixie/deb13). Refresh with
# `apt-cache policy <pkg>` inside the base image when the upstream point
# release bumps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential=12.12 \
        libpq-dev=17.9-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# pip itself is pinned (DL3013). Resolved site-packages are staged under
# /install so the production stage can copy them without dragging the
# compiler toolchain.
RUN pip install "pip==26.0.1" \
 && pip install --prefix=/install -r requirements.txt


FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Runtime libs only. libpq5 is the runtime sibling of libpq-dev used by
# psycopg2. Version pinned (DL3008); refresh alongside libpq-dev above.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5=17.9-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

# Copy installed Python packages from the builder.
COPY --from=builder /install /usr/local

# Refresh packaging tools in the runtime image as well. The base image ships
# older pip/setuptools/wheel under /usr/local, and Trivy scans those packages
# even though application dependencies are copied from the builder.
RUN pip install "pip==26.0.1" "setuptools==82.0.1" "wheel==0.46.3"

# Copy the application source.
COPY --chown=app:app . .

# Bake static assets into the image instead of running collectstatic at boot.
# core.settings.dev points at SQLite + local FS, which is enough for the
# build-time staticfiles pass (no DB or S3 credentials needed). entrypoint.sh
# is made executable in the same layer so there's one RUN for app setup.
ENV DJANGO_SETTINGS_MODULE=core.settings.dev
RUN chmod +x entrypoint.sh \
 && mkdir -p data \
 && chown app:app data \
 && python manage.py collectstatic --noinput

USER app

EXPOSE 8000

# Matches the ECS task-definition liveness probe so local `docker run` shows
# the same container health signal.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/livez/')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
