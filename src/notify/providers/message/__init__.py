import os

from django.conf import settings


def _normalize_provider(provider: str | None) -> str:
    if provider:
        return provider
    env_provider = os.environ.get("SMS_PROVIDER")
    if env_provider:
        return env_provider
    return getattr(settings, "SMS_PROVIDER", "console")


def send_sms(
    target: str,
    message: str,
    provider: str | None = None,
) -> tuple[bool, str]:
    """
    Send an SMS using the configured provider.

    Currently supports a console provider for development/testing.
    """
    provider_name = _normalize_provider(provider).lower()

    if provider_name == "console":
        print(f"[SMS][console] To: {target}\n\n{message}")
        return True, "console"

    # Placeholder for future providers (Twilio, etc.)
    return False, provider_name
