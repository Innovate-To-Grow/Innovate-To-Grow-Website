# syntax=docker/dockerfile:1.7
# Pin the base image by major-minor and (ideally) digest. Production images
# should use a specific @sha256 digest once CI pins are in place; until then
# the tag is updated through Dependabot/Renovate for visibility.
FROM python:3.14-slim AS builder

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


FROM python:3.14-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

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

# Copy the application source.
COPY --chown=app:app . .

# Bake static assets into the image instead of running collectstatic at boot.
# core.settings.dev points at SQLite + local FS, which is enough for the
# build-time staticfiles pass (no DB or S3 credentials needed). entrypoint.sh
# is made executable in the same layer so there's one RUN for app setup.
ENV DJANGO_SETTINGS_MODULE=core.settings.dev
RUN chmod +x entrypoint.sh \
 && python manage.py collectstatic --noinput

USER app

EXPOSE 8000

# Matches the ECS task-definition health probe so local `docker run` shows
# the same readiness signal.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
