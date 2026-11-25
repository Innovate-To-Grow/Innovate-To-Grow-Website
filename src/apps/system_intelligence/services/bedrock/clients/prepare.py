from apps.core.utils.access import user_can_access_app
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.query_tools import get_tool_definitions

from ._aws import get_client
from .exceptions import BedrockError
from .parameters import inference_config


def build_kwargs(chat_config, model_id, *, user=None):
    """Build common kwargs shared by converse and converse_stream."""
    kwargs = {
        "modelId": model_id,
        "inferenceConfig": inference_config(
            model_id=model_id, max_tokens=chat_config.max_tokens, temperature=chat_config.temperature
        ),
    }
    if chat_config.system_prompt:
        kwargs["system"] = [{"text": chat_config.system_prompt}]
    tool_defs = get_tool_definitions() if user_can_access_app(user, "system_intelligence") else []
    if tool_defs:
        kwargs["toolConfig"] = {"tools": tool_defs}
    return kwargs


def prepare(conversation_messages, chat_config, aws_config, model_id=None, *, user=None):
    """Validate configs and return (client, messages, kwargs)."""
    if chat_config is None:
        chat_config = SystemIntelligenceConfig.load()
    if not chat_config.is_configured:
        raise BedrockError("AI Chat is not configured. Add an active AI Chat Config first.")
    if not model_id:
        model_id = chat_config.default_model_id
    client = get_client(aws_config)
    messages = [{"role": m["role"], "content": [{"text": m["content"]}]} for m in conversation_messages]
    return client, messages, build_kwargs(chat_config, model_id, user=user)
