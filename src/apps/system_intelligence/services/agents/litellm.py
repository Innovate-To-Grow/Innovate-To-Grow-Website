import logging
import os

from apps.core.models import AWSCredentialConfig
from apps.core.services.bedrock import normalize_bedrock_model_id

from .errors import SystemIntelligenceAgentError

logger = logging.getLogger(__name__)


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


def bedrock_litellm_credentials(aws_config: AWSCredentialConfig) -> dict[str, str]:
    """Per-call AWS credentials for LiteLLM's Bedrock provider.

    Returned dict is threaded through ``ModelSettings.extra_args`` ->
    ``litellm.acompletion(**kwargs)`` so each model call carries its own
    credentials. This deliberately avoids mutating process-global ``os.environ``:
    doing so could leak the System Intelligence IAM identity into other AWS clients
    in the same process (S3/SES/SNS) and forced a process-wide lock to be held
    across the entire Bedrock network round-trip, serializing all inference.
    """
    if not aws_config.is_configured:
        raise SystemIntelligenceAgentError(
            "AWS credentials are not configured. Add an active AWS Credential Config first."
        )
    return {
        "aws_access_key_id": aws_config.access_key_id,
        "aws_secret_access_key": aws_config.secret_access_key,
        "aws_region_name": aws_config.region,
    }


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
