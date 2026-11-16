"""AI search over the projects catalog.

``search`` prepares and runs a search, ``prompt`` builds what the model is asked and reads the ids in its answer,
``candidates`` picks the projects the model is offered and turns its answer into results. Their names are re-exported
here, so callers keep naming this package; tests patch ``find_ai_search_candidates`` and ``run_tool_free_agent`` in
``search``, where the search looks them up.
"""

from .candidates import (
    AI_SEARCH_SCOPES,
    SCOPE_ALL,
    SCOPE_PAST,
    AISearchCandidate,
    ai_search_results,
    find_ai_search_candidates,
    past_project_ai_queryset,
)
from .prompt import canonical_project_ids
from .search import (
    DEFAULT_AI_SEARCH_LIMIT,
    MAX_AI_SEARCH_LIMIT,
    PreparedPastProjectAISearch,
    prepare_past_project_ai_search,
    run_past_project_ai_search,
)

__all__ = [
    "AISearchCandidate",
    "AI_SEARCH_SCOPES",
    "DEFAULT_AI_SEARCH_LIMIT",
    "MAX_AI_SEARCH_LIMIT",
    "PreparedPastProjectAISearch",
    "SCOPE_ALL",
    "SCOPE_PAST",
    "ai_search_results",
    "canonical_project_ids",
    "find_ai_search_candidates",
    "past_project_ai_queryset",
    "prepare_past_project_ai_search",
    "run_past_project_ai_search",
]
