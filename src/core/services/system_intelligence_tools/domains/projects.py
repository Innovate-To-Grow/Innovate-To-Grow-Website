from typing import Any

from django.db.models import Count

from core.services.system_intelligence_actions.exceptions import ActionRequestError

from ..query_helpers import object_payload, queryset_payload, require_one
from ..runtime import run_action_service_async

PROJECT_FIELDS = [
    "id",
    "semester_id",
    "class_code",
    "team_number",
    "team_name",
    "project_title",
    "organization",
    "industry",
    "abstract",
    "student_names",
    "track",
    "presentation_order",
    "created_at",
    "updated_at",
]


async def get_project_detail(
    project_id: str | None = None, title: str | None = None, team_number: str | None = None
) -> dict[str, Any]:
    """Get one archived project by id, title, or team number."""
    return await run_action_service_async(_get_project_detail, project_id, title, team_number)


async def get_semester_project_summary(
    semester_id: str | None = None,
    year: int | None = None,
    season: str | int | None = None,
) -> dict[str, Any]:
    """Summarize archived projects for a semester."""
    return await run_action_service_async(_get_semester_project_summary, semester_id, year, season)


async def get_current_project_schedule(
    schedule_id: str | None = None, active_only: bool | None = True
) -> dict[str, Any]:
    """Get current project schedule configuration and presenting projects."""
    return await run_action_service_async(_get_current_project_schedule, schedule_id, active_only)


def _find_project(project_id: str | None = None, title: str | None = None, team_number: str | None = None):
    from projects.models import Project

    qs = Project.objects.select_related("semester")
    if project_id:
        return require_one(qs.filter(pk=project_id), "Project")
    if title:
        return require_one(qs.filter(project_title__icontains=title), "Project")
    if team_number:
        return require_one(qs.filter(team_number=team_number), "Project")
    raise ActionRequestError("Provide project_id, title, or team_number.")


def _get_project_detail(project_id=None, title=None, team_number=None) -> dict[str, Any]:
    project = _find_project(project_id, title, team_number)
    return {
        "project": object_payload(project, PROJECT_FIELDS),
        "semester": object_payload(project.semester, ["id", "year", "season", "label", "is_published"]),
    }


def _season_value(season: str | int | None):
    if season is None:
        return None
    if isinstance(season, int):
        return season
    normalized = str(season).strip().lower()
    if normalized in {"1", "spring"}:
        return 1
    if normalized in {"2", "fall"}:
        return 2
    raise ActionRequestError("season must be Spring, Fall, 1, or 2.")


def _find_semester(semester_id=None, year=None, season=None):
    from projects.models import Semester

    qs = Semester.objects.all()
    if semester_id:
        return require_one(qs.filter(pk=semester_id), "Semester")
    if year is not None:
        qs = qs.filter(year=year)
        season_value = _season_value(season)
        if season_value is not None:
            qs = qs.filter(season=season_value)
        return require_one(qs.order_by("-season"), "Semester")
    return require_one(qs.order_by("-year", "-season"), "Semester")


def _get_semester_project_summary(semester_id=None, year=None, season=None) -> dict[str, Any]:
    semester = _find_semester(semester_id, year, season)
    projects = semester.projects.all()
    by_class = list(projects.values("class_code").annotate(count=Count("id")).order_by("class_code"))
    by_industry = list(projects.values("industry").annotate(count=Count("id")).order_by("-count", "industry")[:20])
    return {
        "semester": object_payload(semester, ["id", "year", "season", "label", "is_published"]),
        "project_count": projects.count(),
        "by_class_code": by_class,
        "top_industries": by_industry,
        "sample_projects": queryset_payload(
            projects.order_by("class_code", "team_number"),
            ["id", "class_code", "team_number", "team_name", "project_title", "organization", "industry"],
            limit=20,
        )["rows"],
    }


def _get_current_project_schedule(schedule_id=None, active_only=True) -> dict[str, Any]:
    from event.models import CurrentProjectSchedule

    qs = CurrentProjectSchedule.objects.prefetch_related("projects")
    if schedule_id:
        schedule = require_one(qs.filter(pk=schedule_id), "Current project schedule")
    elif active_only:
        schedule = require_one(qs.filter(is_active=True), "Active current project schedule")
    else:
        schedule = require_one(qs.order_by("-updated_at"), "Current project schedule")
    projects = schedule.projects.all()
    return {
        "schedule": object_payload(
            schedule,
            [
                "id",
                "name",
                "is_active",
                "show_winners",
                "last_synced_at",
                "sync_error",
                "auto_sync_enabled",
                "sync_interval_minutes",
                "updated_at",
            ],
        ),
        "project_count": projects.count(),
        "presenting_count": projects.filter(is_presenting=True).count(),
        "projects": queryset_payload(
            projects.order_by("class_code", "team_number"),
            ["id", "class_code", "team_number", "team_name", "project_title", "organization", "is_presenting"],
            limit=30,
        )["rows"],
    }
