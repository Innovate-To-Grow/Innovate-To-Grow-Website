"""What the model is asked for an AI search, and how the project ids in its answer are read."""

import json
import logging
import re
import uuid
from collections.abc import Iterable

from apps.projects.services.ai_search.candidates import SCOPE_ALL, SCOPE_PAST, AISearchCandidate

logger = logging.getLogger(__name__)
_SYSTEM_TEXT = (
    "You are a read-only project search assistant for Innovate to Grow. "
    "Your only job is to select matching project IDs from the supplied candidate list."
)
# What the prompt asks for, by scope: the archive's past projects, or this semester's projects as well.
_PROMPT_SUBJECTS = {
    SCOPE_PAST: "the past Innovate to Grow projects",
    SCOPE_ALL: "the Innovate to Grow projects, this semester's and past ones,",
}


def _candidate_line(candidate: AISearchCandidate) -> str:
    abstract = (candidate.abstract or "").replace("\n", " ").strip()
    if len(abstract) > 420:
        abstract = abstract[:420].rstrip() + "..."
    parts = [
        f"id={candidate.id}",
        f"title={candidate.project_title}",
        f"semester={candidate.semester_label}",
        f"class={candidate.class_code}",
        f"team_number={candidate.team_number}",
        f"team_name={candidate.team_name}",
        f"organization={candidate.organization}",
        f"industry={candidate.industry}",
    ]
    if abstract:
        parts.append(f"abstract={abstract}")
    return " | ".join(parts)


def _build_prompt(*, query: str, candidates: list[AISearchCandidate], limit: int, scope: str) -> str:
    candidate_lines = "\n".join(f"- {_candidate_line(candidate)}" for candidate in candidates)
    return (
        f"Choose {_PROMPT_SUBJECTS[scope]} that best match the user's search query.\n"
        "Use ONLY the candidate project IDs below. Do not invent IDs. Do not include explanations.\n"
        "Each ID is the UUID after id= in a candidate line; return the UUID alone, without the id= prefix.\n"
        f'Return valid JSON only in this exact shape: {{"ids": ["<candidate UUID>"], "reason": "short summary"}}.\n'
        f"Return at most {limit} IDs, ordered from most relevant to least relevant.\n\n"
        f"Search query: {query}\n\n"
        f"Candidate projects:\n{candidate_lines}"
    )


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


_ID_PREFIX_RE = re.compile(r"^id\s*[=:]\s*", re.IGNORECASE)


def canonical_project_ids(values: Iterable, allowed: frozenset[str] | None = None) -> list[str]:
    """The project UUIDs among ``values`` (model output), canonical and de-duplicated, in order.

    Anything else the model may return (the prompt's placeholder, an echoed "id=" prefix, a number, an object) is
    dropped rather than reaching a UUID lookup, and with ``allowed`` so is any id that was not a candidate.
    """
    ids: list[str] = []
    for value in values:
        if not isinstance(value, str | uuid.UUID):
            continue
        try:
            project_id = str(uuid.UUID(_ID_PREFIX_RE.sub("", str(value).strip())))
        except ValueError:
            continue
        if project_id in ids or (allowed is not None and project_id not in allowed):
            continue
        ids.append(project_id)
    return ids


def _parse_ids(text: str, allowed: frozenset[str] | None = None) -> list[str]:
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
    ids = canonical_project_ids(raw_ids, allowed)
    if len(ids) < len(raw_ids):
        logger.warning(
            "Past project AI search dropped ids that are repeated or not candidate UUIDs: %s", str(raw_ids)[:500]
        )
    return ids
