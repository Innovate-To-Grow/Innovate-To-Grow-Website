import json
import logging
import re
from collections.abc import Iterable

from django.db.models import Q, QuerySet

from apps.core.models import AWSCredentialConfig
from apps.core.services.bedrock import BedrockError, normalize_bedrock_model_id
from apps.core.services.bedrock.clients import get_client
from apps.projects.models import Project, Semester
from apps.system_intelligence.models import SystemIntelligenceConfig

logger = logging.getLogger(__name__)

DEFAULT_AI_SEARCH_LIMIT = 10
MAX_AI_SEARCH_LIMIT = 10
_CANDIDATE_LIMIT = 80
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.&/-]*", re.IGNORECASE)
_STOP_WORDS = {
    "a",
    "about",
    "and",
    "are",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "past",
    "project",
    "projects",
    "the",
    "to",
    "with",
}


def past_project_ai_queryset() -> QuerySet[Project]:
    """Published past projects, matching /projects/past-all/ semantics."""
    newest_pk = Semester.objects.filter(is_published=True).values("pk")[:1]
    return (
        Project.objects.filter(semester__is_published=True)
        .exclude(semester__pk__in=newest_pk)
        .select_related("semester")
        .order_by("-semester__year", "-semester__season", "class_code", "team_number")
    )


def _tokens(query: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for match in _TOKEN_RE.findall(query.lower()):
        token = match.strip("-/.&")
        if len(token) < 2 or token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _candidate_filter(tokens: Iterable[str]) -> Q:
    query = Q()
    for token in tokens:
        query |= Q(project_title__icontains=token)
        query |= Q(organization__icontains=token)
        query |= Q(industry__icontains=token)
        query |= Q(class_code__icontains=token)
        query |= Q(team_number__icontains=token)
        query |= Q(team_name__icontains=token)
        query |= Q(abstract__icontains=token)
        query |= Q(student_names__icontains=token)
    return query


def find_ai_search_candidates(query: str, *, candidate_limit: int = _CANDIDATE_LIMIT) -> list[Project]:
    tokens = _tokens(query)
    if not tokens:
        return []
    project_filter = _candidate_filter(tokens)
    if not project_filter:
        return []
    return list(past_project_ai_queryset().filter(project_filter).distinct()[:candidate_limit])


def _candidate_line(project: Project) -> str:
    abstract = (project.abstract or "").replace("\n", " ").strip()
    if len(abstract) > 420:
        abstract = abstract[:420].rstrip() + "..."
    parts = [
        f"id={project.id}",
        f"title={project.project_title}",
        f"semester={project.semester.label}",
        f"class={project.class_code}",
        f"team_number={project.team_number}",
        f"team_name={project.team_name}",
        f"organization={project.organization}",
        f"industry={project.industry}",
    ]
    if abstract:
        parts.append(f"abstract={abstract}")
    return " | ".join(parts)


def _build_prompt(*, query: str, candidates: list[Project], limit: int) -> str:
    candidate_lines = "\n".join(f"- {_candidate_line(project)}" for project in candidates)
    return (
        "Choose the past Innovate to Grow projects that best match the user's search query.\n"
        "Use ONLY the candidate project IDs below. Do not invent IDs. Do not include explanations.\n"
        f'Return valid JSON only in this exact shape: {{"ids": ["project-id"], "reason": "short summary"}}.\n'
        f"Return at most {limit} IDs, ordered from most relevant to least relevant.\n\n"
        f"Search query: {query}\n\n"
        f"Candidate projects:\n{candidate_lines}"
    )


def _extract_text(response) -> str:
    content = response["output"]["message"]["content"]
    return "".join(block["text"] for block in content if "text" in block)


def _json_fragment(text: str):
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped
    object_start = stripped.find("{")
    object_end = stripped.rfind("}")
    if object_start != -1 and object_end > object_start:
        return stripped[object_start : object_end + 1]
    list_start = stripped.find("[")
    list_end = stripped.rfind("]")
    if list_start != -1 and list_end > list_start:
        return stripped[list_start : list_end + 1]
    return stripped


def _parse_ids(text: str) -> list[str]:
    try:
        payload = json.loads(_json_fragment(text))
    except json.JSONDecodeError:
        logger.warning("Past project AI search returned non-JSON output: %s", text[:500])
        return []
    if isinstance(payload, dict):
        raw_ids = payload.get("ids") or payload.get("project_ids") or payload.get("results") or []
    else:
        raw_ids = payload
    if not isinstance(raw_ids, list):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for value in raw_ids:
        project_id = str(value).strip()
        if not project_id or project_id in seen:
            continue
        seen.add(project_id)
        ids.append(project_id)
    return ids


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


def run_past_project_ai_search(*, query: str, limit: int, config: SystemIntelligenceConfig) -> dict:
    limit = min(max(1, limit), MAX_AI_SEARCH_LIMIT)
    candidates = find_ai_search_candidates(query)
    if not candidates:
        return {"project_ids": [], "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}}

    normalized_model_id = normalize_bedrock_model_id(config.public_model_id)
    if not normalized_model_id:
        raise BedrockError("No valid public assistant model is configured.")

    system_text = (
        "You are a read-only project search assistant for Innovate to Grow. "
        "Your only job is to select matching project IDs from the supplied candidate list."
    )
    prompt = _build_prompt(query=query, candidates=candidates, limit=limit)
    client = get_client(AWSCredentialConfig.load())
    base_kwargs = {
        "modelId": normalized_model_id,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "system": [{"text": system_text}],
    }
    inference = {
        "maxTokens": min(config.public_assistant_max_response_tokens, 700),
        "temperature": config.public_assistant_temperature,
    }

    try:
        response = client.converse(**base_kwargs, inferenceConfig=inference)
    except Exception as exc:  # noqa: BLE001
        if not _is_temperature_error(exc):
            raise BedrockError(f"Past project AI search error: {exc}") from exc
        try:
            response = client.converse(
                **base_kwargs,
                inferenceConfig={"maxTokens": min(config.public_assistant_max_response_tokens, 700)},
            )
        except Exception as retry_exc:  # noqa: BLE001
            raise BedrockError(f"Past project AI search error: {retry_exc}") from retry_exc

    text = _extract_text(response)
    usage = response.get("usage") or _estimate_usage(system_text, prompt, text)
    return {"project_ids": _parse_ids(text)[:limit], "usage": usage}
