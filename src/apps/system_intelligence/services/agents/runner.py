import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import SystemIntelligenceConfig

from .agent_builder import build_agent, build_model_settings
from .agent_builder import build_agent_tools as build_agent_tools  # agents/__init__ and tests import it from here
from .constants import (
    MAX_LLM_CALLS,
)
from .events import StreamState, normalize_agent_stream_event, usage_event
from .litellm import bedrock_litellm_credentials, build_litellm_model


@dataclass
class AgentTextResult:
    text: str
    usage: dict[str, int]


async def run_agent_invocation(
    previous_messages: Iterable[dict[str, str]],
    user_message: str,
    *,
    chat_config: SystemIntelligenceConfig,
    aws_config: AWSCredentialConfig,
    model_id: str,
    user_id: str,
    include_temperature: bool,
    mode: str = "normal",
):
    agent = build_agent_callable()(
        chat_config=chat_config,
        aws_config=aws_config,
        model_id=model_id,
        include_temperature=include_temperature,
        mode=mode,
    )
    input_items = normalize_input_messages([*previous_messages, {"role": "user", "content": user_message}])
    state = StreamState()
    result = runner_class().run_streamed(
        agent,
        input=input_items,
        max_turns=MAX_LLM_CALLS,
        run_config=build_run_config(),
    )
    async for stream_event in result.stream_events():
        for event in normalize_agent_stream_event(stream_event, state):
            yield event
    final_usage = usage_event(getattr(getattr(result, "context_wrapper", None), "usage", None))
    if final_usage:
        yield final_usage


def build_agent_callable():
    import apps.system_intelligence.services.agents as package

    return getattr(package, "_build_agent", build_agent)


def runner_class():
    from agents import Runner

    return Runner


def build_run_config():
    from agents import RunConfig

    return RunConfig(trace_include_sensitive_data=False)


def normalize_input_messages(messages: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for message in messages:
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def run_tool_free_agent(
    *,
    system_text: str,
    input_data: str | list[dict[str, str]],
    aws_config: AWSCredentialConfig,
    model_id: str,
    max_tokens: int,
    temperature: float | None,
    include_temperature: bool = True,
    agent_name: str = "system_intelligence_tool_free",
) -> AgentTextResult:
    return asyncio.run(
        run_tool_free_agent_async(
            system_text=system_text,
            input_data=input_data,
            aws_config=aws_config,
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            include_temperature=include_temperature,
            agent_name=agent_name,
        )
    )


async def run_tool_free_agent_async(
    *,
    system_text: str,
    input_data: str | list[dict[str, str]],
    aws_config: AWSCredentialConfig,
    model_id: str,
    max_tokens: int,
    temperature: float | None,
    include_temperature: bool = True,
    agent_name: str = "system_intelligence_tool_free",
) -> AgentTextResult:
    from agents import Agent

    model = build_litellm_model(aws_config=aws_config, model_id=model_id)
    agent = Agent(
        name=agent_name,
        instructions=system_text,
        model=model,
        model_settings=build_model_settings(
            max_tokens=max_tokens,
            temperature=temperature,
            include_temperature=include_temperature,
            extra_args=bedrock_litellm_credentials(aws_config),
            model_id=model_id,
        ),
        tools=[],
    )
    result = await runner_class().run(
        agent,
        input=input_data,
        max_turns=1,
        run_config=build_run_config(),
    )
    return AgentTextResult(
        text=str(getattr(result, "final_output", "") or "").strip(),
        usage=usage_payload(getattr(getattr(result, "context_wrapper", None), "usage", None)),
    )


def usage_payload(usage: Any) -> dict[str, int]:
    event = usage_event(usage) or {}
    return {
        "inputTokens": int(event.get("inputTokens") or 0),
        "outputTokens": int(event.get("outputTokens") or 0),
        "totalTokens": int(event.get("totalTokens") or 0),
    }
