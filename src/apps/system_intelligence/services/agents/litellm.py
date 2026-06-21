import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from apps.core.models import AWSCredentialConfig
from apps.core.services.bedrock import normalize_bedrock_model_id

from .errors import SystemIntelligenceAgentError

logger = logging.getLogger(__name__)

_AWS_ENV_KEYS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
    "AWS_REGION_NAME",
)
_AWS_ENV_LOCK = threading.RLock()


def build_litellm_model(*, aws_config: AWSCredentialConfig, model_id: str):
    configure_litellm_bedrock_transport()
    configure_agents_tracing()
    from agents.extensions.models.litellm_model import LitellmModel

    if not aws_config.is_configured:
        raise SystemIntelligenceAgentError(
            "AWS credentials are not configured. Add an active AWS Credential Config first."
        )
    return LitellmModel(model=to_litellm_bedrock_model(model_id))


def to_litellm_bedrock_model(model_id: str) -> str:
    normalized_model_id = normalize_bedrock_model_id(model_id)
    if not normalized_model_id:
        raise SystemIntelligenceAgentError("A Bedrock model ID is required for System Intelligence.")
    return f"bedrock/{normalized_model_id}"


@contextmanager
def bedrock_litellm_environment(aws_config: AWSCredentialConfig) -> Iterator[None]:
    """Expose the active AWS config to LiteLLM for the duration of one model call."""
    if not aws_config.is_configured:
        raise SystemIntelligenceAgentError(
            "AWS credentials are not configured. Add an active AWS Credential Config first."
        )
    next_values = {
        "AWS_ACCESS_KEY_ID": aws_config.access_key_id,
        "AWS_SECRET_ACCESS_KEY": aws_config.secret_access_key,
        "AWS_DEFAULT_REGION": aws_config.region,
        "AWS_REGION": aws_config.region,
        "AWS_REGION_NAME": aws_config.region,
    }
    with _AWS_ENV_LOCK:
        previous_values = {key: os.environ.get(key) for key in _AWS_ENV_KEYS}
        os.environ.update(next_values)
        try:
            yield
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def configure_agents_tracing() -> None:
    try:
        from agents import set_tracing_disabled
    except Exception:
        logger.debug("OpenAI Agents tracing configuration skipped", exc_info=True)
        return
    set_tracing_disabled(True)


def configure_litellm_bedrock_transport() -> None:
    """Avoid aiodns/c-ares resolver failures in LiteLLM's async Bedrock path."""
    os.environ.setdefault("DISABLE_AIOHTTP_TRANSPORT", "True")
    try:
        import litellm
    except Exception:
        logger.debug("LiteLLM transport configuration skipped", exc_info=True)
    else:
        litellm.disable_aiohttp_transport = True
        litellm.use_aiohttp_transport = False
    prefer_threaded_aiohttp_resolver()


def prefer_threaded_aiohttp_resolver() -> None:
    """Prefer the stdlib resolver when aiohttp is used by any dependency."""
    try:
        import aiohttp.connector
        import aiohttp.resolver
    except Exception:
        logger.debug("aiohttp resolver patch skipped", exc_info=True)
        return
    aiohttp.connector.DefaultResolver = aiohttp.resolver.ThreadedResolver
    aiohttp.resolver.DefaultResolver = aiohttp.resolver.ThreadedResolver
