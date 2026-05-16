import uuid
from collections.abc import Iterable

from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from core.models import AWSCredentialConfig
from system_intelligence.models import SystemIntelligenceConfig
from system_intelligence.services.tools import get_adk_tools

from .constants import (
    AGENT_NAME,
    APP_NAME,
    APPROVAL_INSTRUCTION,
    MAX_LLM_CALLS,
    PLAN_MODE_INSTRUCTION,
    READ_ONLY_ADK_WEB_INSTRUCTION,
)
from .events import StreamState, normalize_adk_event
from .history import seed_session_history
from .litellm import build_lite_llm_model

PLAN_MODE = "plan"


async def run_adk_invocation(
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
    runner, session_service = build_runner_callable()(
        chat_config=chat_config,
        aws_config=aws_config,
        model_id=model_id,
        include_temperature=include_temperature,
        mode=mode,
    )
    session = await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=f"si-{uuid.uuid4()}")
    await seed_session_history(session_service, session, previous_messages)
    state = StreamState()
    new_message = types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    run_config = RunConfig(streaming_mode=StreamingMode.SSE, max_llm_calls=MAX_LLM_CALLS)
    async for adk_event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=new_message,
        run_config=run_config,
    ):
        for event in normalize_adk_event(adk_event, state):
            yield event


def build_runner_callable():
    import system_intelligence.services.adk as package

    return getattr(package, "_build_runner", build_runner)


def build_runner(
    *,
    chat_config: SystemIntelligenceConfig,
    aws_config: AWSCredentialConfig,
    model_id: str,
    include_temperature=True,
    mode: str = "normal",
    include_writes: bool = True,
    include_exports: bool = True,
):
    session_service = InMemorySessionService()
    agent = build_agent(
        chat_config=chat_config,
        aws_config=aws_config,
        model_id=model_id,
        include_temperature=include_temperature,
        mode=mode,
        include_writes=include_writes,
        include_exports=include_exports,
    )
    return Runner(agent=agent, app_name=APP_NAME, session_service=session_service), session_service


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
    model = build_lite_llm_model(aws_config=aws_config, model_id=model_id)
    generate_content_config = build_generate_content_config(chat_config, include_temperature=include_temperature)
    instruction = (chat_config.system_prompt or "") + (
        APPROVAL_INSTRUCTION if include_writes else READ_ONLY_ADK_WEB_INSTRUCTION
    )
    tool_include_writes = include_writes
    if mode == PLAN_MODE:
        instruction += PLAN_MODE_INSTRUCTION
        tool_include_writes = False
    tools = get_adk_tools(include_writes=tool_include_writes, include_exports=include_exports)
    return LlmAgent(
        name=AGENT_NAME,
        description="Administrative assistant for Innovate to Grow operational data.",
        model=model,
        instruction=instruction,
        tools=tools,
        generate_content_config=generate_content_config,
    )


def build_generate_content_config(chat_config: SystemIntelligenceConfig, *, include_temperature: bool):
    kwargs = {"maxOutputTokens": chat_config.max_tokens}
    if include_temperature:
        kwargs["temperature"] = chat_config.temperature
    return types.GenerateContentConfig(**kwargs)
