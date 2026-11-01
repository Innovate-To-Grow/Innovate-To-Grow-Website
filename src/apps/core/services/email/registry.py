"""Email provider registration and configuration resolution."""

from collections.abc import Callable

from apps.core.services.aws.provider_outcomes import NO_PROVIDER_RETRIES

from .contracts import EmailProvider
from .exceptions import EmailDeliveryError, PermanentEmailDeliveryError
from .gmail import GmailProvider
from .graph import GraphProvider
from .ses import SESProvider
from .smtp import SMTPProvider

ProviderFactory = Callable[[object], EmailProvider]
_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory, *, replace: bool = False) -> None:
    """Register a provider factory by its normalized configuration value."""
    key = name.strip().lower()
    if not key:
        raise ValueError("Provider name cannot be blank.")
    if key in _REGISTRY and not replace:
        raise ValueError(f"Email provider {key!r} is already registered.")
    _REGISTRY[key] = factory


def resolve_provider(config: object, **provider_options) -> EmailProvider:
    """Resolve exactly the configured provider; providers never fall back."""
    name = str(getattr(config, "provider", "")).strip().lower()
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise PermanentEmailDeliveryError(f"Unsupported email provider: {name or '(blank)'}.") from exc
    return factory(config, **provider_options)


def _ses_factory(config: object, **provider_options) -> SESProvider:
    return SESProvider(
        from_email=config.from_email,
        from_name=config.from_name,
        configuration_set=provider_options.get("configuration_set")
        or getattr(config, "configuration_set", None)
        or None,
        # One attempt per admission: botocore's own retries would send past the limiter (SES throttles answer fast).
        retry_config=provider_options.get("retry_config") or NO_PROVIDER_RETRIES,
    )


def _smtp_factory(config: object, **provider_options) -> SMTPProvider:
    del provider_options
    from apps.core.models import SMTPProviderConfig

    smtp = SMTPProviderConfig.load()
    if not smtp.is_configured:
        raise PermanentEmailDeliveryError("Active SMTP provider configuration is missing or invalid.")
    return SMTPProvider(
        host=smtp.host,
        port=smtp.port,
        from_email=config.from_email,
        from_name=config.from_name,
        username=smtp.username,
        password=smtp.password,
        use_tls=smtp.use_tls,
        use_ssl=getattr(smtp, "use_ssl", False),
        timeout=getattr(smtp, "timeout", 30),
    )


def _graph_factory(config: object, **provider_options) -> GraphProvider:
    del provider_options
    from apps.core.models import MicrosoftGraphProviderConfig

    from .graph.access import SEND, credential_for, require_mailbox

    graph = MicrosoftGraphProviderConfig.load()
    if not graph.is_configured:
        raise PermanentEmailDeliveryError("Active Microsoft Graph provider configuration is missing or invalid.")
    # Graph sends as the URL mailbox and Exchange checks Send As for the From address, so both must be in scope.
    mailbox = require_mailbox(graph, graph.sender_mailbox(config.from_email), SEND)
    require_mailbox(graph, config.from_email, SEND)
    return GraphProvider(
        credential=credential_for(graph),
        mailbox=mailbox,
        from_email=config.from_email,
        from_name=config.from_name,
    )


def _gmail_factory(config: object, **provider_options) -> GmailProvider:
    del provider_options
    from apps.core.models import GmailApiProviderConfig

    from .gmail.access import credential_for, require_subject

    gmail = GmailApiProviderConfig.load()
    if not gmail.is_configured:
        raise PermanentEmailDeliveryError("Active Gmail API provider configuration is missing or invalid.")
    # Gmail sends as the JWT subject and only From that same account, so one allow-list check covers both. It runs
    # on every send, so removing an account takes effect at once, even while a token for it is cached.
    subject = require_subject(gmail, config.from_email)
    return GmailProvider(
        credential=credential_for(gmail),
        subject=subject,
        from_email=config.from_email,
        from_name=config.from_name,
        max_recipients=gmail.max_recipients_per_message,
        max_message_bytes=gmail.max_message_bytes,
        credential_mail=gmail.credential_mail,
    )


def active_rate_target() -> tuple[str, str] | None:
    """The active email delivery channel and identity (``delivery_rates.families``), or None while email is not set
    up. Registered for the email family in ``CoreConfig.ready``."""
    from apps.core.models import EmailServiceConfig

    config = EmailServiceConfig.load()
    if not config.is_active:
        return None
    try:
        provider = resolve_provider(config)
    except EmailDeliveryError:
        return None
    return provider.rate_channel, provider.rate_identity()


register_provider("ses", _ses_factory)
register_provider("smtp", _smtp_factory)
register_provider("graph", _graph_factory)
register_provider("gmail", _gmail_factory)
