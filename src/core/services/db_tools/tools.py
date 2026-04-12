"""Tool function implementations for each Bedrock tool-use action."""

import importlib
import json
from datetime import datetime

from django.db.models import Count, Q

from .helpers import MAX_ROWS, _serialize_rows, _truncate


def _search_members(params):
    from authn.models import Member

    qs = Member.objects.all()
    if params.get("name"):
        terms = params["name"].split()
        for t in terms:
            qs = qs.filter(Q(first_name__icontains=t) | Q(last_name__icontains=t))
    if params.get("email"):
        qs = qs.filter(contactemail__email_address__icontains=params["email"])
    if params.get("organization"):
        qs = qs.filter(organization__icontains=params["organization"])
    if params.get("is_staff") is not None:
        qs = qs.filter(is_staff=params["is_staff"])
    if params.get("is_active") is not None:
        qs = qs.filter(is_active=params["is_active"])
    qs = qs.distinct()
    return _serialize_rows(
        qs, ["id", "first_name", "last_name", "organization", "title", "is_staff", "is_active", "created_at"]
    )


def _count_members(params):
    from authn.models import Member

    qs = Member.objects.all()
    if params.get("is_staff") is not None:
        qs = qs.filter(is_staff=params["is_staff"])
    if params.get("is_active") is not None:
        qs = qs.filter(is_active=params["is_active"])
    if params.get("organization"):
        qs = qs.filter(organization__icontains=params["organization"])
    return f"Count: {qs.count()}"


def _search_events(params):
    from event.models import Event

    qs = Event.objects.all()
    if params.get("name"):
        qs = qs.filter(name__icontains=params["name"])
    if params.get("is_live") is not None:
        qs = qs.filter(is_live=params["is_live"])
    if params.get("date_from"):
        qs = qs.filter(date__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(date__lte=params["date_to"])
    qs = qs.order_by("-date")
    return _serialize_rows(qs, ["id", "name", "slug", "date", "location", "is_live"])


def _get_event_registrations(params):
    from event.models import EventRegistration

    qs = EventRegistration.objects.all()
    if params.get("event_name"):
        qs = qs.filter(event__name__icontains=params["event_name"])
    if params.get("event_id"):
        qs = qs.filter(event_id=params["event_id"])
    if params.get("count_only"):
        return f"Registration count: {qs.count()}"
    return _serialize_rows(
        qs,
        [
            "id",
            "attendee_first_name",
            "attendee_last_name",
            "attendee_email",
            "attendee_organization",
            "event__name",
            "ticket__name",
            "created_at",
        ],
    )


def _search_projects(params):
    from projects.models import Project

    qs = Project.objects.all()
    if params.get("title"):
        qs = qs.filter(project_title__icontains=params["title"])
    if params.get("team_name"):
        qs = qs.filter(team_name__icontains=params["team_name"])
    if params.get("organization"):
        qs = qs.filter(organization__icontains=params["organization"])
    if params.get("industry"):
        qs = qs.filter(industry__icontains=params["industry"])
    if params.get("semester"):
        qs = qs.filter(
            Q(semester__label__icontains=params["semester"]) | Q(semester__season__icontains=params["semester"])
        )
    if params.get("class_code"):
        qs = qs.filter(class_code__icontains=params["class_code"])
    qs = qs.select_related("semester").order_by("-semester__year", "team_number")
    return _serialize_rows(
        qs,
        [
            "id",
            "project_title",
            "team_name",
            "team_number",
            "class_code",
            "organization",
            "industry",
            "student_names",
            "semester__label",
        ],
    )


def _search_email_campaigns(params):
    from mail.models import EmailCampaign

    qs = EmailCampaign.objects.all()
    if params.get("name"):
        qs = qs.filter(name__icontains=params["name"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    if params.get("subject"):
        qs = qs.filter(subject__icontains=params["subject"])
    qs = qs.order_by("-created_at")
    return _serialize_rows(
        qs,
        [
            "id",
            "name",
            "subject",
            "status",
            "audience_type",
            "total_recipients",
            "sent_count",
            "failed_count",
            "sent_at",
            "created_at",
        ],
    )


def _get_campaign_stats(params):
    from mail.models import EmailCampaign, RecipientLog

    qs = EmailCampaign.objects.all()
    if params.get("campaign_name"):
        qs = qs.filter(name__icontains=params["campaign_name"])
    if params.get("campaign_id"):
        qs = qs.filter(id=params["campaign_id"])
    campaign = qs.first()
    if not campaign:
        return "No campaign found matching the criteria."
    logs = RecipientLog.objects.filter(campaign=campaign)
    stats = logs.values("status").annotate(count=Count("id"))
    return (
        f"Campaign: {campaign.name}\n"
        f"Subject: {campaign.subject}\n"
        f"Status: {campaign.status}\n"
        f"Total recipients: {campaign.total_recipients}\n"
        f"Sent: {campaign.sent_count}, Failed: {campaign.failed_count}\n"
        f"Delivery breakdown: {json.dumps(list(stats), default=str)}"
    )


def _search_cms_pages(params):
    from cms.models import CMSPage

    qs = CMSPage.objects.all()
    if params.get("title"):
        qs = qs.filter(title__icontains=params["title"])
    if params.get("slug"):
        qs = qs.filter(slug__icontains=params["slug"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    qs = qs.order_by("sort_order")
    return _serialize_rows(
        qs,
        ["id", "title", "slug", "route", "status", "meta_description", "published_at"],
    )


def _search_news(params):
    from cms.models import NewsArticle

    qs = NewsArticle.objects.all()
    if params.get("title"):
        qs = qs.filter(title__icontains=params["title"])
    if params.get("source"):
        qs = qs.filter(source__icontains=params["source"])
    if params.get("date_from"):
        qs = qs.filter(published_at__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(published_at__lte=params["date_to"])
    qs = qs.order_by("-published_at")
    return _serialize_rows(
        qs,
        ["id", "title", "source", "author", "source_url", "published_at", "summary"],
    )


def _get_page_views(params):
    from cms.models import PageView

    qs = PageView.objects.all()
    if params.get("path"):
        qs = qs.filter(path__icontains=params["path"])
    if params.get("date_from"):
        qs = qs.filter(timestamp__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(timestamp__lte=params["date_to"])
    if params.get("count_only"):
        return f"Page view count: {qs.count()}"
    from django.db.models.functions import TruncDate

    by_date = qs.annotate(day=TruncDate("timestamp")).values("day").annotate(views=Count("id")).order_by("-day")[:30]
    top_pages = qs.values("path").annotate(views=Count("id")).order_by("-views")[:20]
    return _truncate(
        f"Total views: {qs.count()}\n\n"
        f"Views by date (last 30 days):\n{json.dumps(list(by_date), default=str)}\n\n"
        f"Top pages:\n{json.dumps(list(top_pages), default=str)}"
    )


def _get_checkin_stats(params):
    from event.models import CheckInRecord

    qs = CheckInRecord.objects.all()
    if params.get("event_name"):
        qs = qs.filter(check_in__event__name__icontains=params["event_name"])
    if params.get("event_id"):
        qs = qs.filter(check_in__event_id=params["event_id"])
    total = qs.count()
    by_checkin = qs.values("check_in__name", "check_in__event__name").annotate(count=Count("id")).order_by("-count")
    return _truncate(f"Total check-ins: {total}\n" f"By station:\n{json.dumps(list(by_checkin), default=str)}")


def _search_semesters(params):
    from projects.models import Semester

    qs = Semester.objects.all()
    if params.get("year"):
        qs = qs.filter(year=params["year"])
    if params.get("season"):
        qs = qs.filter(season__icontains=params["season"])
    if params.get("is_published") is not None:
        qs = qs.filter(is_published=params["is_published"])
    qs = qs.order_by("-year", "season")
    return _serialize_rows(qs, ["id", "year", "season", "label", "is_published"])


def _run_custom_query(params):
    """Flexible query tool with an allowlist of models."""
    MODEL_MAP = {
        "Member": ("authn.models", "Member"),
        "ContactEmail": ("authn.models", "ContactEmail"),
        "ContactPhone": ("authn.models", "ContactPhone"),
        "Event": ("event.models", "Event"),
        "EventRegistration": ("event.models", "EventRegistration"),
        "Ticket": ("event.models", "Ticket"),
        "CheckIn": ("event.models", "CheckIn"),
        "CheckInRecord": ("event.models", "CheckInRecord"),
        "Project": ("projects.models", "Project"),
        "Semester": ("projects.models", "Semester"),
        "EmailCampaign": ("mail.models", "EmailCampaign"),
        "RecipientLog": ("mail.models", "RecipientLog"),
        "CMSPage": ("cms.models", "CMSPage"),
        "CMSBlock": ("cms.models", "CMSBlock"),
        "NewsArticle": ("cms.models", "NewsArticle"),
        "NewsFeedSource": ("cms.models", "NewsFeedSource"),
        "PageView": ("cms.models", "PageView"),
        "Menu": ("cms.models", "Menu"),
    }

    model_name = params.get("model", "")
    if model_name not in MODEL_MAP:
        return f"Unknown model '{model_name}'. Available: {', '.join(sorted(MODEL_MAP))}"

    module_path, cls_name = MODEL_MAP[model_name]
    mod = importlib.import_module(module_path)
    model_cls = getattr(mod, cls_name)

    qs = model_cls.objects.all()

    filters = params.get("filters", {})
    if isinstance(filters, dict) and filters:
        try:
            qs = qs.filter(**filters)
        except Exception as exc:
            return f"Filter error: {exc}"

    ordering = params.get("ordering")
    if ordering:
        if isinstance(ordering, str):
            ordering = [ordering]
        try:
            qs = qs.order_by(*ordering)
        except Exception as exc:
            return f"Ordering error: {exc}"

    if params.get("count_only"):
        return f"Count: {qs.count()}"

    fields = params.get("fields")
    limit = min(params.get("limit", MAX_ROWS), MAX_ROWS)

    if fields and isinstance(fields, list):
        return _serialize_rows(qs, fields, limit)

    rows = list(qs.values()[:limit])
    for row in rows:
        for k, v in row.items():
            if isinstance(v, datetime):
                row[k] = v.isoformat()
            elif hasattr(v, "hex"):
                row[k] = str(v)
    count = qs.count()
    header = f"Showing {min(count, limit)} of {count} result(s) from {model_name}.\n"
    return _truncate(header + json.dumps(rows, indent=2, default=str))


TOOL_REGISTRY = {
    "search_members": _search_members,
    "count_members": _count_members,
    "search_events": _search_events,
    "get_event_registrations": _get_event_registrations,
    "search_projects": _search_projects,
    "search_email_campaigns": _search_email_campaigns,
    "get_campaign_stats": _get_campaign_stats,
    "search_cms_pages": _search_cms_pages,
    "search_news": _search_news,
    "get_page_views": _get_page_views,
    "get_checkin_stats": _get_checkin_stats,
    "search_semesters": _search_semesters,
    "run_custom_query": _run_custom_query,
}
