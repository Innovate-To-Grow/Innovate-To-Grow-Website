import logging
import os
import re
import smtplib
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template import Context, Engine
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import escape, strip_tags
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[a-z][\s\S]*>", re.IGNORECASE)
_HTML_DOC_RE = re.compile(r"<!doctype|<html", re.IGNORECASE)
_SUBJECT_ENGINE = Engine(autoescape=True)
_BODY_ENGINE = Engine(autoescape=False)

if TYPE_CHECKING:
    from notify.models import EmailLayout, GoogleGmailAccount


def _normalize_provider(provider: str | None) -> str:
    if provider:
        return provider
    env_provider = os.environ.get("EMAIL_PROVIDER")
    if env_provider:
        return env_provider
    return getattr(settings, "EMAIL_PROVIDER", "console")


def _looks_like_html(body: str) -> bool:
    return bool(_HTML_TAG_RE.search(body or ""))


def _is_html_document(body: str) -> bool:
    return bool(_HTML_DOC_RE.search(body or ""))


def _build_plain_text(body: str) -> str:
    return strip_tags(body or "").strip()


def _coerce_html(body: str) -> str:
    if not body:
        return ""
    if _looks_like_html(body):
        return body
    safe = escape(body).replace("\n", "<br>")
    return f"<p>{safe}</p>"


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


def _resolve_user_name(email: str) -> str:
    try:
        user_model = get_user_model()
    except Exception:
        return ""

    user = user_model.objects.filter(email__iexact=email).first()
    if not user:
        return ""

    if hasattr(user, "get_full_name"):
        full_name = user.get_full_name()
        if full_name:
            full_name = full_name.strip()
            if full_name:
                return full_name

    parts = []
    for attr in ("first_name", "middle_name", "last_name"):
        value = getattr(user, attr, "")
        if value:
            parts.append(value)
    full_name = " ".join(part for part in parts if part).strip()
    if full_name:
        return full_name

    username = getattr(user, "username", "")
    return username or ""


def _normalize_context(context: dict[str, Any] | None, target: str) -> dict[str, Any]:
    ctx = dict(context or {})
    if "recipient_name" not in ctx:
        if "user_name" in ctx:
            ctx["recipient_name"] = ctx["user_name"]
        else:
            resolved_name = _resolve_user_name(target)
            ctx["recipient_name"] = resolved_name or _derive_name_from_email(target)
    if "user_name" not in ctx:
        ctx["user_name"] = ctx["recipient_name"]
    ctx.setdefault("recipient_email", target)
    return ctx


def _get_layout_from_db(
    layout: "EmailLayout | None" = None,
    layout_key: str | None = None,
) -> "EmailLayout | None":
    if layout is not None:
        return layout
    try:
        from notify.models import EmailLayout
    except Exception:
        return None

    if layout_key:
        return EmailLayout.objects.filter(key=layout_key, is_active=True).first()

    default_layout = EmailLayout.objects.filter(is_default=True, is_active=True).first()
    if default_layout:
        return default_layout
    return EmailLayout.objects.filter(is_active=True).first()


def render_email_layout(
    *,
    subject: str,
    body: str,
    context: dict[str, Any] | None = None,
    layout: "EmailLayout | None" = None,
    layout_key: str | None = None,
) -> tuple[str, str]:
    """
    Render HTML + plaintext email using the shared layout template.
    """
    if _is_html_document(body):
        html_body = body
        text_body = _build_plain_text(body)
        return html_body, text_body

    body_html = _coerce_html(body)
    text_body = _build_plain_text(body_html)
    preheader = text_body.replace("\n", " ").strip()[:140]

    brand_name = os.environ.get("EMAIL_BRAND_NAME") or getattr(settings, "EMAIL_BRAND_NAME", None) or "Innovate To Grow"
    brand_color = os.environ.get("EMAIL_BRAND_COLOR") or getattr(settings, "EMAIL_BRAND_COLOR", None) or "#1f4e79"
    site_url = getattr(settings, "SITE_URL", "") or os.environ.get("SITE_URL", "")
    support_email = (
        os.environ.get("SUPPORT_EMAIL")
        or getattr(settings, "SUPPORT_EMAIL", "")
        or os.environ.get("DEFAULT_FROM_EMAIL")
        or getattr(settings, "DEFAULT_FROM_EMAIL", "")
    )
    footer_text = (
        os.environ.get("EMAIL_FOOTER_TEXT")
        or getattr(settings, "EMAIL_FOOTER_TEXT", None)
        or "You are receiving this email because you interacted with Innovate To Grow."
    )
    logo_url = os.environ.get("EMAIL_LOGO_URL") or getattr(settings, "EMAIL_LOGO_URL", "")

    template_context = {
        "subject": subject,
        "body_html": mark_safe(body_html),
        "brand_name": brand_name,
        "brand_color": brand_color,
        "site_url": site_url,
        "support_email": support_email,
        "footer_text": footer_text,
        "logo_url": logo_url,
        "preheader": preheader,
        "year": timezone.now().year,
    }
    if context:
        template_context.update(context)

    layout_obj = _get_layout_from_db(layout=layout, layout_key=layout_key)
    if layout_obj and layout_obj.html_template:
        html_body = _render_template(layout_obj.html_template, template_context, autoescape=False)
    else:
        html_body = render_to_string("notify/email/base.html", template_context)
    return html_body, text_body


def _smtp_connection_from_account(account: "GoogleGmailAccount"):
    """Create an SMTP connection from a database GoogleGmailAccount."""
    use_ssl = not account.use_tls and account.smtp_port == 465
    return get_connection(
        host=account.smtp_host,
        port=account.smtp_port,
        username=account.gmail_address,
        password=account.google_app_password,
        use_tls=account.use_tls,
        use_ssl=use_ssl,
    )


def _smtp_connection_from_env():
    """
    Create an SMTP connection from environment variables.

    Falls back to env vars when no GoogleGmailAccount exists in the DB
    (e.g., fresh deployment). Returns ``(connection, from_address)`` or
    ``(None, None)`` if the required env vars are not set.
    """
    smtp_user = os.environ.get("EMAIL_SMTP_USER", "")
    smtp_pass = os.environ.get("EMAIL_SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        return None, None

    host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    use_tls = port != 465
    use_ssl = port == 465

    from_address = os.environ.get("DEFAULT_FROM_EMAIL") or getattr(settings, "DEFAULT_FROM_EMAIL", smtp_user)

    connection = get_connection(
        host=host,
        port=port,
        username=smtp_user,
        password=smtp_pass,
        use_tls=use_tls,
        use_ssl=use_ssl,
    )
    return connection, from_address


def _resolve_gmail_account(
    gmail_account_id: int | None = None,
) -> "GoogleGmailAccount | None":
    """
    Resolve a GoogleGmailAccount to use for sending.

    Priority:
    1. Explicit ``gmail_account_id`` if provided
    2. Default active account from the database
    3. ``None`` (fall back to Django settings)
    """
    try:
        from notify.models import GoogleGmailAccount
    except Exception:
        return None

    if gmail_account_id:
        try:
            return GoogleGmailAccount.objects.get(pk=gmail_account_id, is_active=True, is_deleted=False)
        except GoogleGmailAccount.DoesNotExist:
            logger.warning("Gmail account %s not found or inactive", gmail_account_id)
            return None

    return GoogleGmailAccount.get_default()


def send_email(
    target: str,
    subject: str,
    body: str,
    provider: str | None = None,
    from_email: str | None = None,
    context: dict[str, Any] | None = None,
    layout: "EmailLayout | None" = None,
    layout_key: str | None = None,
    gmail_account_id: int | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> tuple[bool, str]:
    """
    Send an email using the configured provider.

    Args:
        target: Recipient email address.
        subject: Email subject (may contain Django template variables).
        body: Email body (may contain Django template variables).
        provider: "console", "gmail", "smtp", or ``None`` for auto-detect.
        from_email: Explicit sender address (overrides account / settings).
        context: Template rendering context dict.
        layout: An ``EmailLayout`` instance to wrap the body with.
        layout_key: Key to look up an ``EmailLayout`` from the database.
        gmail_account_id: ID of a ``GoogleGmailAccount`` to use for SMTP.
        attachments: List of ``(filename, content_bytes, mimetype)`` tuples.
        cc: List of Cc recipient email addresses.
        bcc: List of Bcc recipient email addresses.

    Returns:
        ``(success, provider_name)``
    """
    provider_name = _normalize_provider(provider).lower()

    if provider_name == "console":
        ctx = _normalize_context(context, target)
        rendered_subject = _render_template(subject, ctx, autoescape=True)
        rendered_body = _render_template(body, ctx, autoescape=False)
        print(f"[EMAIL][console] To: {target}\nSubject: {rendered_subject}\n\n{rendered_body}")
        if cc:
            print(f"[EMAIL][console] Cc: {cc}")
        if bcc:
            print(f"[EMAIL][console] Bcc: {bcc}")
        if attachments:
            print(f"[EMAIL][console] Attachments: {[a[0] for a in attachments]}")
        return True, "console"

    if provider_name in {"gmail", "smtp"}:
        # Resolve Gmail account from DB, fall back to env vars
        account = _resolve_gmail_account(gmail_account_id)
        if account:
            connection = _smtp_connection_from_account(account)
            from_address = from_email or account.get_from_email()
        else:
            connection, env_from = _smtp_connection_from_env()
            if not connection:
                logger.error(
                    "No active Gmail account in the database and EMAIL_SMTP_USER/EMAIL_SMTP_PASS "
                    "env vars not set. Cannot send email to %s",
                    target,
                )
                return False, provider_name
            from_address = from_email or env_from
            logger.info("Using SMTP credentials from environment variables (no DB account found)")

        ctx = _normalize_context(context, target)
        rendered_subject = _render_template(subject, ctx, autoescape=True)
        rendered_body = _render_template(body, ctx, autoescape=False)
        html_body, text_body = render_email_layout(
            subject=rendered_subject,
            body=rendered_body,
            context=ctx,
            layout=layout,
            layout_key=layout_key,
        )

        message = EmailMultiAlternatives(
            subject=rendered_subject,
            body=text_body or rendered_body,
            from_email=from_address,
            to=[target],
            cc=cc or [],
            bcc=bcc or [],
            connection=connection,
        )
        if html_body:
            message.attach_alternative(html_body, "text/html")

        if attachments:
            for filename, content, mimetype in attachments:
                message.attach(filename, content, mimetype)

        try:
            message.send()
        except smtplib.SMTPAuthenticationError:
            error_msg = "Authentication failed. Check Gmail address and App Password."
            logger.error("SMTP auth failed sending to %s: %s", target, error_msg)
            if account:
                account.mark_used(error=error_msg)
            return False, provider_name
        except (smtplib.SMTPConnectError, ConnectionRefusedError):
            error_msg = "Could not connect to SMTP server."
            logger.error("SMTP connection failed sending to %s: %s", target, error_msg)
            if account:
                account.mark_used(error=error_msg)
            return False, provider_name
        except smtplib.SMTPRecipientsRefused:
            error_msg = "Invalid recipient address."
            logger.error("SMTP recipients refused for %s: %s", target, error_msg)
            if account:
                account.mark_used(error=error_msg)
            return False, provider_name
        except smtplib.SMTPException as exc:
            error_msg = f"SMTP error: {exc}"
            logger.error("SMTP error sending to %s: %s", target, error_msg)
            if account:
                account.mark_used(error=error_msg)
            return False, provider_name
        except Exception as exc:
            logger.exception("Unexpected error sending email to %s", target)
            if account:
                account.mark_used(error=str(exc))
            return False, provider_name

        if account:
            account.mark_used()
        return True, provider_name

    # Unknown provider: fallback to console for safety
    ctx = _normalize_context(context, target)
    rendered_subject = _render_template(subject, ctx, autoescape=True)
    rendered_body = _render_template(body, ctx, autoescape=False)
    print(f"[EMAIL][{provider_name}] To: {target}\nSubject: {rendered_subject}\n\n{rendered_body}")
    return True, provider_name
