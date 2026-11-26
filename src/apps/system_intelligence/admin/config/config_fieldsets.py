"""The System Intelligence configuration change form, as tabs: one per audience, then the public spend limits."""

from django.utils.translation import gettext_lazy as _

TAB = ["tab"]

CONFIG_FIELDSETS = (
    (None, {"fields": ("name", "is_active")}),
    (
        _("Admin Assistant"),
        {
            "classes": TAB,
            "description": "The staff assistant in System Intelligence → Chat. The same provider and model also "
            "write context summaries and the inbox scam review. A blank provider means Amazon Bedrock through the "
            "active AWS Credential Config; other providers are managed under AI Providers.",
            "fields": ("default_provider", "default_model_id", "temperature", "max_tokens", "system_prompt"),
        },
    ),
    (
        _("Public Assistant"),
        {
            "classes": TAB,
            "description": "The public, visitor-facing chatbot and past-project AI search. It is tool-free and "
            "read-only: it never reaches the admin assistant, its tools or private data. A blank Public Assistant "
            "Model uses the admin assistant's provider and model.",
            "fields": (
                "public_assistant_enabled",
                "public_assistant_provider",
                "public_assistant_model_id",
                "public_assistant_temperature",
                "public_assistant_max_response_tokens",
                "public_assistant_system_prompt",
                "public_assistant_welcome_message",
                "public_assistant_starter_questions",
                "public_assistant_unavailable_message",
            ),
        },
    ),
    (
        _("Public Limits"),
        {
            "classes": TAB,
            "description": "Message size and spend limits for the public chatbot and past-project AI search.",
            "fields": (
                "public_assistant_max_message_chars",
                "public_assistant_max_history_messages",
                "public_assistant_ip_token_limit",
                "public_assistant_ip_token_window_seconds",
                "public_assistant_global_token_limit",
                "public_assistant_global_usage",
            ),
        },
    ),
    (
        _("Audit Logging"),
        {"classes": TAB, "fields": ("public_assistant_log_enabled", "public_assistant_log_retention_days")},
    ),
    (_("Info"), {"classes": TAB, "fields": ("id", "created_at", "updated_at")}),
)
