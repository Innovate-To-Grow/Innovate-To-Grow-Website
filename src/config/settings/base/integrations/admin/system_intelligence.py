"""System Intelligence in the admin: its sidebar section and its Usage & Logs tab group.

The sidebar lists Chat, AI Providers (``LLMProviderConfig``), Assistant Settings (``SystemIntelligenceConfig``) and
Usage & Logs. Usage & Logs opens the usage dashboard (a custom page); its tabs also hold the conversation logs, the
message logs and the action requests the assistant proposed, and its sidebar entry stays highlighted on all of them.
The sidebar shows at most one entry per tab group, so the two configuration pages are separate entries, not tabs.
"""

from apps.core.utils.access import user_can_access_app

CHAT_PATH = "/admin/system-intelligence/"
USAGE_PATH = "/admin/system-intelligence/usage/"
SETTINGS_PATH = "/admin/system_intelligence/systemintelligenceconfig/"
PROVIDERS_PATH = "/admin/system_intelligence/llmproviderconfig/"
CONVERSATION_LOGS_PATH = "/admin/system_intelligence/assistantconversationlog/"
MESSAGE_LOGS_PATH = "/admin/system_intelligence/assistantmessagelog/"
ACTION_REQUESTS_PATH = "/admin/system_intelligence/systemintelligenceactionrequest/"
USAGE_PAGE = "system_intelligence_usage"

_USAGE_GROUP_PATHS = (USAGE_PATH, CONVERSATION_LOGS_PATH, MESSAGE_LOGS_PATH, ACTION_REQUESTS_PATH)

USAGE_TABS = [
    {"title": "Usage Dashboard", "link": USAGE_PATH},
    {"title": "Conversation Logs", "link": CONVERSATION_LOGS_PATH},
    {"title": "Message Logs", "link": MESSAGE_LOGS_PATH},
    {"title": "Action Requests", "link": ACTION_REQUESTS_PATH},
]

SYSTEM_INTELLIGENCE_TABS = [
    {
        "models": [
            "system_intelligence.assistantconversationlog",
            "system_intelligence.assistantmessagelog",
            "system_intelligence.systemintelligenceactionrequest",
        ],
        "items": USAGE_TABS,
    },
    {"page": USAGE_PAGE, "items": USAGE_TABS},
]


def _can_use(request):
    return user_can_access_app(request.user, "system_intelligence")


def is_chat(request):
    path = request.path
    return path.startswith(CHAT_PATH) and not path.startswith(USAGE_PATH)


def is_usage_group(request):
    return request.path.startswith(_USAGE_GROUP_PATHS)


SYSTEM_INTELLIGENCE_SECTION = {
    "title": "System Intelligence",
    "permission": _can_use,
    "items": [
        {"title": "Chat", "link": CHAT_PATH, "permission": _can_use, "active": is_chat},
        {"title": "AI Providers", "link": PROVIDERS_PATH, "permission": _can_use},
        {"title": "Assistant Settings", "link": SETTINGS_PATH, "permission": _can_use},
        {"title": "Usage & Logs", "link": USAGE_PATH, "permission": _can_use, "active": is_usage_group},
    ],
}
