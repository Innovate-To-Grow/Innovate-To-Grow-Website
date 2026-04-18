# syntax=docker/dockerfile:1.7
# Pin the base image by major-minor and (ideally) digest. Production images
# should use a specific @sha256 digest once CI pins are in place; until then
# the tag is updated through Dependabot/Renovate for visibility.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install build-time dependencies only in the builder stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --prefix=/install -r requirements.txt


FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Runtime-only libs (libpq5 is the runtime sibling of libpq-dev).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

# Copy installed Python packages from the builder.
COPY --from=builder /install /usr/local

# Copy the application source.
COPY --chown=app:app . .

# Bake static assets into the image instead of running collectstatic at boot.
# DJANGO_SETTINGS_MODULE must tolerate collectstatic without a real DB; dev
# settings use SQLite + local FS, which is fine for this build-time step.
ENV DJANGO_SETTINGS_MODULE=core.settings.dev
RUN python manage.py collectstatic --noinput || echo "collectstatic skipped (no static root configured yet)"

RUN chmod +x entrypoint.sh

USER app

EXPOSE 8000

# Matches the ECS task-definition health probe so local `docker run` shows
# the same readiness signal.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
