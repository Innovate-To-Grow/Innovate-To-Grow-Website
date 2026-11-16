"""Archive project pages for /sitemap.xml (registered in settings.SITEMAP_ENTRY_PROVIDERS)."""

from apps.projects.models import Project


def archive_project_sitemap_entries():
    """``/past-projects/project/<id>`` for every published archive project, with when it last changed."""
    projects = Project.objects.filter(semester__is_published=True).order_by(
        "-semester__year", "-semester__season", "class_code", "team_number", "pk"
    )
    return [(f"/past-projects/project/{pk}", updated_at) for pk, updated_at in projects.values_list("pk", "updated_at")]
