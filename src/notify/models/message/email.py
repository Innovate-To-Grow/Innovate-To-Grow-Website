from django.db import models
from django.template import Context, Engine

from core.models.base.control import ProjectControlModel

_SUBJECT_ENGINE = Engine(autoescape=True)
_BODY_ENGINE = Engine(autoescape=False)


def _render_template(template_str: str, context: dict, *, autoescape: bool) -> str:
    if not template_str:
        return ""
    engine = _SUBJECT_ENGINE if autoescape else _BODY_ENGINE
    template = engine.from_string(template_str)
    return template.render(Context(context))


def _derive_name_from_email(email: str | None) -> str:
    if not email or "@" not in email:
        return "there"
    local = email.split("@", 1)[0].strip()
    if not local:
        return "there"
    name = local.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    return name.title() if name else "there"


class EmailMessageLayout(ProjectControlModel):
    """
    Stores reusable email templates (subject/body) editable in admin.
    """

    layout = models.ForeignKey(
        "notify.EmailLayout",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_layouts",
        help_text="Optional base layout to wrap this message.",
    )
    key = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Unique key used by the code to select this template.",
    )
    name = models.CharField(
        max_length=128,
        help_text="Human-readable name for this email template.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description to help admins understand this template.",
    )
    subject_template = models.CharField(
        max_length=255,
        help_text="Django template string for the email subject.",
    )
    preheader_template = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional preheader text shown in email clients.",
    )
    body_template = models.TextField(
        help_text="Django template string for the email body (HTML allowed).",
    )
    default_context = models.JSONField(
        blank=True,
        default=dict,
        help_text="Default JSON context merged into every render.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only active templates are used for sending.",
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["key"]),
            models.Index(fields=["is_active"]),
        ]
        verbose_name = "Email Message Layout"
        verbose_name_plural = "Email Message Layouts"

    def __str__(self) -> str:
        return f"{self.name} ({self.key})"

    def build_context(self, context: dict | None = None, recipient_email: str | None = None) -> dict:
        ctx: dict = {}
        if self.default_context:
            ctx.update(self.default_context)
        if context:
            ctx.update(context)

        if "recipient_name" not in ctx:
            if "user_name" in ctx:
                ctx["recipient_name"] = ctx["user_name"]
            else:
                ctx["recipient_name"] = _derive_name_from_email(recipient_email)
        if "user_name" not in ctx:
            ctx["user_name"] = ctx["recipient_name"]

        if recipient_email and "recipient_email" not in ctx:
            ctx["recipient_email"] = recipient_email

        return ctx

    def get_preview_context(self) -> dict:
        if self.default_context:
            return dict(self.default_context)
        default_ctx = self.contexts.filter(is_default=True).first()
        if default_ctx:
            return dict(default_ctx.context_data or {})
        first_ctx = self.contexts.first()
        if first_ctx:
            return dict(first_ctx.context_data or {})
        return {}

    def render(self, context: dict | None = None, recipient_email: str | None = None) -> tuple[str, str, str, dict]:
        ctx = self.build_context(context=context, recipient_email=recipient_email)
        subject = _render_template(self.subject_template, ctx, autoescape=True).strip()
        body = _render_template(self.body_template, ctx, autoescape=False)
        preheader = _render_template(self.preheader_template, ctx, autoescape=True).strip()
        return subject, body, preheader, ctx


class EmailMessageContext(ProjectControlModel):
    """
    Saved preview contexts for email templates.
    """

    layout = models.ForeignKey(
        EmailMessageLayout,
        on_delete=models.CASCADE,
        related_name="contexts",
    )
    name = models.CharField(
        max_length=128,
        help_text="Label for this context set (e.g. 'Member Preview').",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description for this context set.",
    )
    context_data = models.JSONField(
        blank=True,
        default=dict,
        help_text="JSON data merged into the template context.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Use this context as the default preview data.",
    )

    class Meta:
        ordering = ["name"]
        unique_together = [("layout", "name")]
        verbose_name = "Email Message Context"
        verbose_name_plural = "Email Message Contexts"

    def __str__(self) -> str:
        return f"{self.layout.key} · {self.name}"
