"""Public component and retention constants for the status service."""

from __future__ import annotations

from dataclasses import dataclass

STATUS_VALUES = {
    "operational",
    "degraded",
    "partial_outage",
    "major_outage",
    "maintenance",
    "unknown",
}

RUN_TTL_SECONDS = 2 * 24 * 60 * 60
SAMPLE_TTL_SECONDS = 8 * 24 * 60 * 60
HISTORY_TTL_SECONDS = 100 * 24 * 60 * 60
PUBLIC_HISTORY_DAYS = 90
PUBLIC_INCIDENT_DAYS = 90
STALE_AFTER_SECONDS = 10 * 60
SCHEDULE_SECONDS = 5 * 60


@dataclass(frozen=True)
class HttpProbeSpec:
    """A fixed, non-user-controlled synthetic probe."""

    check_id: str
    url: str
    kind: str
    marker: str | None = None


@dataclass(frozen=True)
class ComponentSpec:
    """Public component metadata and its fixed user-journey probes."""

    component_id: str
    name: str
    group: str
    production_critical: bool
    http_probes: tuple[HttpProbeSpec, ...]


COMPONENTS: tuple[ComponentSpec, ...] = (
    ComponentSpec(
        component_id="production-website",
        name="Production Website",
        group="production",
        production_critical=True,
        http_probes=(
            HttpProbeSpec(
                "production-website.page",
                "https://i2g.ucmerced.edu/",
                "html",
                "innovate to grow",
            ),
        ),
    ),
    ComponentSpec(
        component_id="production-api",
        name="Production API",
        group="production",
        production_critical=True,
        http_probes=(
            HttpProbeSpec("production-api.liveness", "https://api.i2g.ucmerced.edu/livez/", "health"),
            HttpProbeSpec("production-api.readiness", "https://api.i2g.ucmerced.edu/readyz/", "health"),
        ),
    ),
    ComponentSpec(
        component_id="demo-website",
        name="Demo Website",
        group="demo",
        production_critical=False,
        http_probes=(
            HttpProbeSpec(
                "demo-website.page",
                "https://demo.i2g.ucmerced.edu/",
                "html",
                "innovate to grow",
            ),
        ),
    ),
    ComponentSpec(
        component_id="demo-api",
        name="Demo API",
        group="demo",
        production_critical=False,
        http_probes=(
            HttpProbeSpec("demo-api.liveness", "https://demo-api.i2g.ucmerced.edu/livez/", "health"),
            HttpProbeSpec("demo-api.readiness", "https://demo-api.i2g.ucmerced.edu/readyz/", "health"),
            HttpProbeSpec("demo-api.frontend-proxy", "https://demo.i2g.ucmerced.edu/api/readyz/", "health"),
        ),
    ),
    ComponentSpec(
        component_id="project-archive",
        name="Project Archive",
        group="archive",
        production_critical=False,
        http_probes=(
            HttpProbeSpec("project-archive.liveness", "https://archive.i2g.ucmerced.edu/healthz", "health"),
            HttpProbeSpec("project-archive.readiness", "https://archive.i2g.ucmerced.edu/readyz", "health"),
        ),
    ),
)

COMPONENT_BY_ID = {component.component_id: component for component in COMPONENTS}

STATUS_RANK = {
    "operational": 0,
    "degraded": 1,
    "maintenance": 2,
    "partial_outage": 3,
    "major_outage": 4,
    "unknown": 5,
}
