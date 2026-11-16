"""Preparing and running a past-project AI search: the candidates, the prompt, the model call and its budget."""

from dataclasses import dataclass

from apps.core.models import AWSCredentialConfig
from apps.projects.services.ai_search.candidates import SCOPE_PAST, find_ai_search_candidates
from apps.projects.services.ai_search.prompt import _SYSTEM_TEXT, _build_prompt, _parse_ids
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.agents import run_tool_free_agent
from apps.system_intelligence.services.bedrock import BedrockError, normalize_bedrock_model_id
from apps.system_intelligence.services.public_assistant import estimate_prompt_input_tokens

DEFAULT_AI_SEARCH_LIMIT = 10
MAX_AI_SEARCH_LIMIT = 10
_MAX_OUTPUT_TOKENS = 700


def _estimate_usage(system_text: str, prompt: str, reply_text: str) -> dict:
    input_tokens = (len(system_text) + len(prompt)) // 4
    output_tokens = len(reply_text) // 4
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
    }


def _is_temperature_error(exc: Exception) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if "temperature" in text or "sampling" in text:
            return True
        current = current.__cause__ or current.__context__
    return False


@dataclass(frozen=True)
class PreparedPastProjectAISearch:
    """Everything the model call needs, assembled BEFORE any tokens are spent.

    Building the prompt first lets the caller reserve
    ``estimated_input_tokens + max_tokens`` against the token budgets, so a
    search can no longer be admitted on a nearly-spent budget and then charge
    its whole cost on top (check-then-record overshoot).
    """

    limit: int
    system_text: str
    prompt: str
    max_tokens: int
    estimated_input_tokens: int
    # The ids the prompt offered: the only ones a reply may select. Required, because an empty set selects nothing.
    candidate_ids: frozenset[str]


def prepare_past_project_ai_search(
    *,
    query: str,
    limit: int,
    config: SystemIntelligenceConfig,
    scope: str = SCOPE_PAST,
) -> PreparedPastProjectAISearch | None:
    """Find candidates in ``scope`` and build the prompt. ``None`` when nothing matches (no model call)."""
    limit = min(max(1, limit), MAX_AI_SEARCH_LIMIT)
    candidates = find_ai_search_candidates(query, scope=scope)
    if not candidates:
        return None
    prompt = _build_prompt(query=query, candidates=candidates, limit=limit, scope=scope)
    return PreparedPastProjectAISearch(
        limit=limit,
        system_text=_SYSTEM_TEXT,
        prompt=prompt,
        max_tokens=min(config.public_assistant_max_response_tokens, _MAX_OUTPUT_TOKENS),
        estimated_input_tokens=estimate_prompt_input_tokens(system_text=_SYSTEM_TEXT, prompt=prompt),
        candidate_ids=frozenset(candidate.id for candidate in candidates),
    )


def run_past_project_ai_search(
    *,
    query: str,
    limit: int,
    config: SystemIntelligenceConfig,
    prepared: PreparedPastProjectAISearch | None = None,
) -> dict:
    """Run the search. Pass ``prepared`` to reuse a prompt the caller already budgeted for (its scope's; without
    one, the search ranks the "past" scope)."""
    if prepared is None:
        prepared = prepare_past_project_ai_search(query=query, limit=limit, config=config)
    if prepared is None:
        return {"project_ids": [], "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}}

    normalized_model_id = normalize_bedrock_model_id(config.public_model_id)
    if not normalized_model_id:
        raise BedrockError("No valid public assistant model is configured.")

    limit = prepared.limit
    system_text = prepared.system_text
    prompt = prepared.prompt
    aws_config = AWSCredentialConfig.load()
    max_tokens = prepared.max_tokens

    try:
        result = run_tool_free_agent(
            system_text=system_text,
            input_data=prompt,
            aws_config=aws_config,
            model_id=normalized_model_id,
            max_tokens=max_tokens,
            temperature=config.public_assistant_temperature,
            agent_name="past_project_ai_search",
        )
    except Exception as exc:  # noqa: BLE001
        if not _is_temperature_error(exc):
            raise BedrockError(f"Past project AI search error: {exc}") from exc
        try:
            result = run_tool_free_agent(
                system_text=system_text,
                input_data=prompt,
                aws_config=aws_config,
                model_id=normalized_model_id,
                max_tokens=max_tokens,
                temperature=config.public_assistant_temperature,
                include_temperature=False,
                agent_name="past_project_ai_search",
            )
        except Exception as retry_exc:  # noqa: BLE001
            raise BedrockError(f"Past project AI search error: {retry_exc}") from retry_exc

    text = result.text
    usage = result.usage or {}
    if not usage.get("totalTokens"):
        # usage_payload always returns a (possibly all-zero) dict, so fall back on the
        # char-based estimate whenever the model reported no usable token totals.
        usage = _estimate_usage(system_text, prompt, text)
    return {"project_ids": _parse_ids(text, prepared.candidate_ids)[:limit], "usage": usage}
