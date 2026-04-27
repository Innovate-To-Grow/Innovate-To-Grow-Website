import logging
import os

from core.models import AWSCredentialConfig
from core.services.bedrock import normalize_bedrock_model_id

from .errors import SystemIntelligenceADKError

logger = logging.getLogger(__name__)


def build_lite_llm_model(*, aws_config: AWSCredentialConfig, model_id: str):
    configure_litellm_bedrock_transport()
    from google.adk.models.lite_llm import LiteLlm

    return LiteLlm(
        model=to_litellm_bedrock_model(model_id),
        aws_access_key_id=aws_config.access_key_id,
        aws_secret_access_key=aws_config.secret_access_key,
        aws_region_name=aws_config.default_region or "us-west-2",
    )


def to_litellm_bedrock_model(model_id: str) -> str:
    normalized_model_id = normalize_bedrock_model_id(model_id)
    if not normalized_model_id:
        raise SystemIntelligenceADKError("A Bedrock model ID is required for System Intelligence.")
    return f"bedrock/{normalized_model_id}"


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
