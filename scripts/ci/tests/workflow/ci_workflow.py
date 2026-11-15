from __future__ import annotations

import re
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


BACKEND_VENV_ACTION = REPOSITORY_ROOT / ".github" / "actions" / "setup-backend-venv" / "action.yml"


BACKEND_VENV_USES = "./.github/actions/setup-backend-venv"


BACKEND_DOCKERFILE = REPOSITORY_ROOT / "src" / "Dockerfile"


PLAYWRIGHT_CONFIG = REPOSITORY_ROOT / "pages" / "playwright.config.ts"


COVERAGE_FLOORS = REPOSITORY_ROOT / "scripts" / "ci" / "coverage" / "backend_coverage_floors.json"


DEPENDABOT_CONFIG = REPOSITORY_ROOT / ".github" / "dependabot.yml"


WORKFLOW_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"


DEPLOY_ARCHIVE_WORKFLOW = WORKFLOW_DIRECTORY / "deploy-archive.yml"


TRIVY_ACTION = "aquasecurity/trivy-action@"


TRIVY_RELEASES = "https://github.com/aquasecurity/trivy/releases/download/"


# Any way a job could create a virtualenv itself instead of using setup-backend-venv.
VENV_CREATION = re.compile(r"-m\s+venv\b|\buv\s+venv\b|\bvirtualenv\b")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_ci() -> dict:
    return load_yaml(CI_WORKFLOW)


def steps_of(job: dict) -> list[dict]:
    return job.get("steps") or []


def run_scripts(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in steps_of(job))


def backend_venv_jobs(jobs: dict) -> dict[str, dict]:
    """Jobs that set up the backend virtualenv, mapped to their setup-backend-venv step."""
    return {
        name: step
        for name, job in jobs.items()
        for step in steps_of(job)
        if str(step.get("uses", "")) == BACKEND_VENV_USES
    }


def trivy_scans(job: dict) -> list[dict]:
    return [step for step in steps_of(job) if str(step.get("uses", "")).startswith(TRIVY_ACTION)]
