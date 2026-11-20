from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.core.utils.access import user_can_access_app
from apps.system_intelligence.models import ChatConversation

from ...query_tools.tool_modules.custom.allowlist import MODEL_MAP
from .context import ACTION_CONVERSATION_ID, current_user

_TOOLS_BY_GRANT = {
    ("authn",): (
        "search_members",
        "count_members",
        "search_contact_info",
        "propose_member_update",
        "export_members_to_excel",
    ),
    ("authn", "event", "mail", "cms"): ("get_member_detail", "get_member_activity_summary"),
    ("event",): (
        "search_events",
        "get_event_registrations",
        "get_event_detail",
        "search_event_registrations",
        "get_registration_detail",
        "get_ticket_capacity_summary",
        "get_checkin_breakdown",
        "get_event_question_summary",
        "get_current_project_schedule",
        "get_checkin_stats",
        "propose_event_update",
        "export_events_to_excel",
    ),
    ("projects",): (
        "search_projects",
        "get_project_detail",
        "get_semester_project_summary",
        "search_semesters",
        "propose_project_update",
        "export_projects_to_excel",
    ),
    ("mail",): (
        "search_email_campaigns",
        "get_campaign_stats",
        "get_campaign_recipient_logs",
        "get_failed_recipient_report",
        "propose_campaign_update",
    ),
    ("cms",): (
        "search_cms_pages",
        "search_news",
        "search_menus",
        "get_menu_detail",
        "get_footer_content_detail",
        "get_site_settings_detail",
        "search_cms_assets",
        "get_news_source_detail",
        "get_page_views",
        "get_page_view_summary",
        "get_top_paths",
        "get_page_view_trend",
        "get_cms_page_detail",
        "propose_cms_page_update",
        "propose_menu_update",
        "export_news_to_excel",
    ),
}
STATIC_TOOL_GRANTS = {name: grants for grants, names in _TOOLS_BY_GRANT.items() for name in names}
MODEL_TOOLS = frozenset(
    {
        "get_model_schema",
        "get_record",
        "search_records",
        "propose_db_create",
        "propose_db_update",
        "propose_db_delete",
        "export_records_to_excel",
    }
)
DYNAMIC_TOOLS = MODEL_TOOLS | {"run_custom_query", "list_database_models"}
TOOL_DENIED = "You do not have permission to use this tool."


def _required_grants(name, params, user):
    if name in STATIC_TOOL_GRANTS:
        return STATIC_TOOL_GRANTS[name]
    if name in MODEL_TOOLS:
        app_label = params.get("app_label")
        model_name = params.get("model_name")
        if isinstance(app_label, str) and isinstance(model_name, str):
            try:
                return (apps.get_model(app_label.strip(), model_name.strip())._meta.app_label,)
            except LookupError:
                pass
    elif name == "run_custom_query":
        model_name = params.get("model")
        if isinstance(model_name, str) and model_name in MODEL_MAP:
            return (MODEL_MAP[model_name][0],)
    elif name == "list_database_models":
        return tuple(config.label for config in apps.get_app_configs() if user_can_access_app(user, config.label))
    raise PermissionDenied(TOOL_DENIED)


def has_chat_grants(user, required_apps):
    return all(user_can_access_app(user, app_label) for app_label in required_apps or ())


def _record_grants(conversation_id, user, required):
    with transaction.atomic():
        conversation = (
            ChatConversation.objects.select_for_update()
            .filter(pk=conversation_id, created_by=user, required_tool_apps__isnull=False)
            .first()
        )
        if conversation is None or not has_chat_grants(user, conversation.required_tool_apps):
            raise PermissionDenied(TOOL_DENIED)
        used = sorted(set(conversation.required_tool_apps) | set(required))
        if used != conversation.required_tool_apps:
            conversation.required_tool_apps = used
            conversation.save(update_fields=["required_tool_apps"])


def authorize_tool(name, params, *, user=None):
    user = current_user() if user is None else current_user(user.pk)
    if not user_can_access_app(user, "system_intelligence") or not isinstance(params, dict):
        raise PermissionDenied(TOOL_DENIED)
    required = _required_grants(name, params, user)
    if not has_chat_grants(user, required):
        raise PermissionDenied(TOOL_DENIED)
    conversation_id = ACTION_CONVERSATION_ID.get()
    if conversation_id:
        _record_grants(conversation_id, user, required)
