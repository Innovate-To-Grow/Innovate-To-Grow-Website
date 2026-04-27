from core.models import AWSCredentialConfig

from .constants import BEDROCK_CONNECTIVITY_KEYWORDS, BEDROCK_HOST_RE


class SystemIntelligenceADKError(Exception):
    """Raised when the ADK runtime cannot be configured or invoked."""


def format_system_intelligence_error(
    error: BaseException | str, *, aws_config: AWSCredentialConfig | None = None
) -> str:
    """Return a stable admin-facing error message for provider/runtime failures."""
    message = exception_chain_message(error)
    if is_bedrock_connectivity_error(message):
        region = (
            bedrock_region_from_message(message) or getattr(aws_config, "default_region", None) or "configured region"
        )
        return (
            f"Unable to reach AWS Bedrock Runtime in {region}. "
            "Check network/DNS connectivity for the server and try again."
        )
    return str(error)


def exception_chain_message(error: BaseException | str) -> str:
    if isinstance(error, str):
        return error
    messages = []
    current: BaseException | None = error
    while current is not None:
        messages.append(str(current))
        current = current.__cause__ or current.__context__
    return "\n".join(messages)


def is_bedrock_connectivity_error(message: str) -> bool:
    normalized = message.lower()
    return "bedrock" in normalized and any(keyword in normalized for keyword in BEDROCK_CONNECTIVITY_KEYWORDS)


def bedrock_region_from_message(message: str) -> str | None:
    match = BEDROCK_HOST_RE.search(message)
    return match.group(1) if match else None


def is_temperature_deprecated_error(exc: Exception) -> bool:
    messages = []
    current: BaseException | None = exc
    while current is not None:
        messages.append(str(current).lower())
        current = current.__cause__ or current.__context__
    message = "\n".join(messages)
    return "temperature" in message and "deprecated" in message
