"""Email provider registration and configuration resolution."""

from collections.abc import Callable

from .contracts import EmailProvider
from .exceptions import PermanentEmailDeliveryError
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
        retry_config=provider_options.get("retry_config"),
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


register_provider("ses", _ses_factory)
register_provider("smtp", _smtp_factory)
