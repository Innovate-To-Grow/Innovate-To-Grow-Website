"""Build a compact, public, read-only grounding context for the assistant.

Every source is wrapped in its own try/except so a single failing selector can
never break the whole context build -- an empty context is acceptable. The
final string is hard-truncated to ``char_cap``.
"""

import logging

logger = logging.getLogger(__name__)

# Per-source row caps keep the prompt bounded and cheap regardless of DB size.
_CURRENT_PROJECTS_LIMIT = 20
_PAST_PROJECTS_LIMIT = 15
_NEWS_LIMIT = 8
_CMS_PAGES_LIMIT = 25


def _current_projects_section() -> str:
    from apps.event.models import CurrentProjectSchedule

    config = CurrentProjectSchedule.load()
    if not config:
        return ""
    projects = list(config.projects.order_by("class_code", "team_number")[:_CURRENT_PROJECTS_LIMIT])
    if not projects:
        return ""
    header = f"CURRENT PROJECTS ({config.name or 'this semester'}):"
    lines = [header]
    for project in projects:
        title = project.project_title or "Untitled project"
        bits = [title]
        if project.team_name:
            bits.append(f"team {project.team_name}")
        if project.organization:
            bits.append(f"with {project.organization}")
        if project.industry:
            bits.append(f"({project.industry})")
        lines.append("- " + " ".join(bits))
    return "\n".join(lines)


def _past_projects_section() -> str:
    from apps.projects.models import Project

    projects = list(
        Project.objects.filter(semester__is_published=True)
        .select_related("semester")
        .order_by("-semester__year", "-semester__season", "class_code")[:_PAST_PROJECTS_LIMIT]
    )
    if not projects:
        return ""
    lines = ["PAST PROJECTS (sample of published work):"]
    for project in projects:
        title = project.project_title or "Untitled project"
        semester = getattr(project.semester, "label", "") or ""
        bits = [title]
        if semester:
            bits.append(f"[{semester}]")
        if project.organization:
            bits.append(f"with {project.organization}")
        lines.append("- " + " ".join(bits))
    return "\n".join(lines)


def _news_section() -> str:
    from apps.cms.models import NewsArticle

    articles = list(NewsArticle.objects.order_by("-published_at")[:_NEWS_LIMIT])
    if not articles:
        return ""
    lines = ["RECENT NEWS:"]
    for article in articles:
        date = article.published_at.date().isoformat() if article.published_at else ""
        suffix = f" ({date})" if date else ""
        lines.append(f"- {article.title}{suffix}")
    return "\n".join(lines)


def _cms_pages_section() -> str:
    from apps.cms.models import CMSPage

    pages = list(CMSPage.objects.filter(status="published").order_by("sort_order", "title")[:_CMS_PAGES_LIMIT])
    if not pages:
        return ""
    lines = ["PUBLISHED PAGES (navigation):"]
    for page in pages:
        lines.append(f"- {page.title} ({page.route})")
    return "\n".join(lines)


_SECTIONS = (
    _current_projects_section,
    _past_projects_section,
    _news_section,
    _cms_pages_section,
)


def build_public_context(*, char_cap: int = 6000) -> str:
    """Assemble a compact, plain-text public context summary.

    Returns an empty string if nothing could be gathered. The result is hard
    truncated to ``char_cap`` characters.
    """
    sections: list[str] = []
    for builder in _SECTIONS:
        try:
            section = builder()
        except Exception:
            logger.warning("Public assistant context section %s failed", builder.__name__, exc_info=True)
            continue
        if section:
            sections.append(section)

    context = "\n\n".join(sections)
    if len(context) > char_cap:
        context = context[:char_cap].rstrip()
    return context
