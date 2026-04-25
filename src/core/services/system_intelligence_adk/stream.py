import asyncio
import logging
import queue
import threading
from collections.abc import Iterable

from django.db import close_old_connections

from core.models import AWSCredentialConfig
from core.models.base.system_intelligence import SystemIntelligenceConfig
from core.services import system_intelligence_actions

from .constants import SENTINEL, TEMPERATURE_DEPRECATED_MODEL_IDS
from .errors import SystemIntelligenceADKError, format_system_intelligence_error, is_temperature_deprecated_error
from .history import split_history_and_current_message
from .runner import run_adk_invocation

logger = logging.getLogger(__name__)


def invoke_system_intelligence_stream(
    conversation_messages: Iterable[dict[str, str]],
    *,
    chat_config: SystemIntelligenceConfig | None = None,
    aws_config: AWSCredentialConfig | None = None,
    model_id: str | None = None,
    user_id: str | None = None,
    conversation_id: str | None = None,
):
    """Synchronously yield existing System Intelligence event dicts from ADK."""
    chat_config = chat_config or SystemIntelligenceConfig.load()
    aws_config = get_aws_config(aws_config)
    model_id = model_id or aws_config.default_model_id
    event_queue: queue.Queue = queue.Queue()

    async def produce():
        async for event in async_stream_callable()(
            conversation_messages,
            chat_config=chat_config,
            aws_config=aws_config,
            model_id=model_id,
            user_id=user_id,
            conversation_id=conversation_id,
        ):
            event_queue.put(event)

    def runner():
        close_old_connections()
        try:
            asyncio.run(produce())
        except Exception as exc:
            formatted = format_system_intelligence_error(exc, aws_config=aws_config)
            if formatted != str(exc):
                logger.warning("System Intelligence ADK provider connectivity failed: %s", formatted)
            else:
                logger.exception("System Intelligence ADK stream failed")
            event_queue.put({"type": "error", "error": formatted})
        finally:
            close_old_connections()
            event_queue.put(SENTINEL)

    thread = threading.Thread(target=runner, name="system-intelligence-adk", daemon=True)
    thread.start()
    while True:
        item = event_queue.get()
        if item is SENTINEL:
            break
        yield item
    thread.join(timeout=1)


def async_stream_callable():
    import core.services.system_intelligence_adk as package

    return getattr(package, "_invoke_system_intelligence_stream_async", invoke_system_intelligence_stream_async)


async def invoke_system_intelligence_stream_async(
    conversation_messages: Iterable[dict[str, str]],
    *,
    chat_config: SystemIntelligenceConfig | None = None,
    aws_config: AWSCredentialConfig | None = None,
    model_id: str | None = None,
    user_id: str | None = None,
    conversation_id: str | None = None,
):
    """Run one ADK invocation and yield normalized event dictionaries."""
    previous_messages, user_message = split_history_and_current_message(conversation_messages)
    chat_config = chat_config or SystemIntelligenceConfig.load()
    aws_config = get_aws_config(aws_config)
    model_id = model_id or aws_config.default_model_id
    if not model_id:
        raise SystemIntelligenceADKError("No Bedrock model is configured. Select a default model first.")

    effective_user_id = user_id or "admin"
    include_temperature = model_id not in TEMPERATURE_DEPRECATED_MODEL_IDS
    emitted_event = False
    context_tokens = system_intelligence_actions.set_action_context(conversation_id, effective_user_id)
    try:
        async for event in run_adk_invocation(
            previous_messages,
            user_message,
            chat_config=chat_config,
            aws_config=aws_config,
            model_id=model_id,
            user_id=effective_user_id,
            include_temperature=include_temperature,
        ):
            emitted_event = True
            yield event
    except Exception as exc:
        if emitted_event or not include_temperature or not is_temperature_deprecated_error(exc):
            raise
        TEMPERATURE_DEPRECATED_MODEL_IDS.add(model_id)
        logger.info("Retrying System Intelligence ADK call without temperature for model '%s'.", model_id)
        async for event in run_adk_invocation(
            previous_messages,
            user_message,
            chat_config=chat_config,
            aws_config=aws_config,
            model_id=model_id,
            user_id=effective_user_id,
            include_temperature=False,
        ):
            yield event
    finally:
        system_intelligence_actions.reset_action_context(context_tokens)


def get_aws_config(aws_config: AWSCredentialConfig | None = None) -> AWSCredentialConfig:
    aws_config = aws_config or AWSCredentialConfig.load()
    if not aws_config.is_configured:
        raise SystemIntelligenceADKError(
            "AWS credentials are not configured. Add an active AWS Credential Config first."
        )
    return aws_config
