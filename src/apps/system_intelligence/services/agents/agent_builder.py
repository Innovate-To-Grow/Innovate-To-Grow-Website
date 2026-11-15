from typing import Any

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.bedrock.clients.parameters import supports_temperature

from .constants import (
    AGENT_NAME,
    APPROVAL_INSTRUCTION,
    PLAN_MODE_INSTRUCTION,
    READ_ONLY_AGENT_DEBUG_INSTRUCTION,
)
from .litellm import bedrock_litellm_credentials, build_litellm_model

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
):
    from agents import Agent

    model = build_litellm_model(aws_config=aws_config, model_id=model_id)
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
            extra_args=bedrock_litellm_credentials(aws_config),
            model_id=model_id,
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
        function_tool(tool, strict_mode=False)
        for tool in get_agent_tool_callables(include_writes=include_writes, include_exports=include_exports)
    ]


def build_model_settings(
    *,
    max_tokens: int,
    temperature: float | None,
    include_temperature: bool,
    extra_args: dict[str, Any] | None = None,
    model_id: str = "",
):
    from agents import ModelSettings

    kwargs: dict[str, Any] = {"max_tokens": max_tokens}
    if include_temperature and supports_temperature(model_id):
        kwargs["temperature"] = temperature
    if extra_args:
        # Threaded into litellm.acompletion(**kwargs) by LitellmModel; carries the
        # per-call Bedrock AWS credentials so we never mutate process-global os.environ.
        kwargs["extra_args"] = extra_args
    return ModelSettings(**kwargs)
