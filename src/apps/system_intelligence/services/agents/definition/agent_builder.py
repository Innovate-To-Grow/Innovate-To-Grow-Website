import json
from typing import Any

from asgiref.sync import sync_to_async
from django.core.exceptions import PermissionDenied

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.actions.engine.tool_access import TOOL_DENIED, authorize_tool

from ..providers.capabilities import supports_temperature
from ..providers.litellm_args import wants_stream_usage
from .constants import AGENT_NAME, APPROVAL_INSTRUCTION, PLAN_MODE_INSTRUCTION, READ_ONLY_AGENT_DEBUG_INSTRUCTION
from .litellm import build_litellm_model, litellm_call_args

PLAN_MODE = "plan"


def build_agent(
    *,
    chat_config: SystemIntelligenceConfig,
    aws_config: AWSCredentialConfig,
    model_id: str,
    include_temperature=True,
    mode: str = "normal",
    include_writes: bool = True,
    include_exports: bool = True,
    provider=None,
):
    from agents import Agent

    model = build_litellm_model(aws_config=aws_config, model_id=model_id, provider=provider)
    instruction = (chat_config.system_prompt or "") + (
        APPROVAL_INSTRUCTION if include_writes else READ_ONLY_AGENT_DEBUG_INSTRUCTION
    )
    tool_include_writes = include_writes
    if mode == PLAN_MODE:
        instruction += PLAN_MODE_INSTRUCTION
        tool_include_writes = False
    return Agent(
        name=AGENT_NAME,
        instructions=instruction,
        model=model,
        model_settings=build_model_settings(
            max_tokens=chat_config.max_tokens,
            temperature=chat_config.temperature,
            include_temperature=include_temperature,
            extra_args=litellm_call_args(aws_config, provider),
            model_id=model_id,
            provider=provider,
        ),
        tools=build_agent_tools(include_writes=tool_include_writes, include_exports=include_exports),
    )


def build_agent_tools(*, include_writes: bool = True, include_exports: bool = True):
    from agents import function_tool

    from apps.system_intelligence.services.tools import get_agent_tool_callables

    return [
        # strict_mode=False: several tools accept open ``dict[str, Any]`` / ``list[dict]``
        # params (run_custom_query/search_records filters, propose_* fields, export_*
        # filters). Pydantic renders those with ``additionalProperties: true``, which the
        # Agents SDK strict JSON-schema validator rejects with a UserError at construction.
        _guard_tool(function_tool(tool, strict_mode=False))
        for tool in get_agent_tool_callables(include_writes=include_writes, include_exports=include_exports)
    ]


def _guard_tool(tool):
    invoke = tool.on_invoke_tool

    async def invoke_authorized(context, arguments):
        try:
            await sync_to_async(authorize_tool)(tool.name, json.loads(arguments or "{}"))
        except (PermissionDenied, ValueError):
            return {"result": TOOL_DENIED}
        return await invoke(context, arguments)

    tool.on_invoke_tool = invoke_authorized
    return tool


def build_model_settings(
    *,
    max_tokens: int,
    temperature: float | None,
    include_temperature: bool,
    extra_args: dict[str, Any] | None = None,
    model_id: str = "",
    provider=None,
):
    from agents import ModelSettings

    kwargs: dict[str, Any] = {"max_tokens": max_tokens}
    if include_temperature and supports_temperature(model_id, provider):
        kwargs["temperature"] = temperature
    if wants_stream_usage(provider):
        kwargs["include_usage"] = True
    if extra_args:
        # Threaded into litellm.acompletion(**kwargs) by LitellmModel; carries the per-call
        # Bedrock AWS credentials (or a provider's timeout) so we never mutate os.environ.
        kwargs["extra_args"] = extra_args
    return ModelSettings(**kwargs)
