# syntax=docker/dockerfile:1.7
# Pin the base image by major-minor and (ideally) digest. Production images
# should use a specific @sha256 digest once CI pins are in place; until then
# the tag is updated through Dependabot/Renovate for visibility.
FROM python:3.11-slim-trixie AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Keep distro-specific security floors tied to Debian trixie. Their own COPY
# layer invalidates cached package installation whenever a requirement changes.
COPY security/ /opt/itg-security/

# Build-time dependencies, pinned to a major version to satisfy DL3008.
#
# Deliberately NOT pinned to an exact patch: Debian keeps only the newest build of
# a package in the archive, so an exact pin like `libpq-dev=17.10-0+deb13u1` stops
# resolving the moment trixie ships a point release — and it fails hard, because
# libpq-dev depends on `libpq5 (= <same exact version>)`. That broke every image
# build when libpq5 moved to 17.11-0+deb13u1. A major-version pin still fixes the
# ABI we build against while tracking security updates within the release.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential=12.* \
        libpq-dev=17.* \
    && sh /opt/itg-security/install-debian-floors.sh \
    && rm -rf /var/lib/apt/lists/*

# Copy the dependency manifests together so their nested `-r` includes resolve.
COPY requirements.txt .
COPY requirements/ requirements/

# pip itself is pinned (DL3013). Resolved site-packages are staged under
# /install so the production stage can copy them without dragging the
# compiler toolchain.
RUN pip install "pip==26.2.0" \
 && pip install --prefix=/install -r requirements/production.txt


FROM python:3.11-slim-trixie AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY security/ /opt/itg-security/

# Runtime libs only. libpq5 is the runtime sibling of libpq-dev used by
# psycopg2. Major-version pinned for the same reason as libpq-dev above — the two
# stages run their own `apt-get update`, so exact pins can also disagree if Debian
# publishes between the two layers.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5=17.* \
    && sh /opt/itg-security/install-debian-floors.sh \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

# Copy installed Python packages from the builder.
COPY --from=builder /install /usr/local

# Refresh packaging tools in the runtime image as well. The base image ships
# older pip/setuptools/wheel under /usr/local, and Trivy scans those packages
# even though application dependencies are copied from the builder.
#
# pip >= 26.2 ships a CycloneDX SBOM of its vendored libraries
# (pip/_vendor/bom.cdx.json). Trivy parses that file and reports the vendored
# setuptools/msgpack versions as if they were installed packages, so drop it —
# the vendored copies are private to pip and not importable by the app.
RUN pip install "pip==26.2.0" "setuptools==83.0.0" "wheel==0.46.3" \
 && find /usr/local/lib -path "*/pip/_vendor/*" -name "*.cdx.json" -delete

# Copy the application source.
COPY --chown=app:app . .

# Bake static assets into the image instead of running collectstatic at boot.
# config.settings.local points at SQLite + local FS, which is enough for the
# build-time staticfiles pass (no DB or S3 credentials needed). entrypoint.sh
# is made executable in the same layer so there's one RUN for app setup.
ENV DJANGO_SETTINGS_MODULE=config.settings.local
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
