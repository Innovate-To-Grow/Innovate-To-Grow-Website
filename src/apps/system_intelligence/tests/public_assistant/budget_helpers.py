"""Shared constants for the public-assistant budget tests."""

from apps.system_intelligence.services.public_assistant import budget

ASSISTANT = budget.FEATURE_ASSISTANT


AI_SEARCH = budget.FEATURE_AI_SEARCH


ASSISTANT_GLOBAL_KEY = budget.GLOBAL_BUDGET_KEYS[ASSISTANT]


AI_SEARCH_GLOBAL_KEY = budget.GLOBAL_BUDGET_KEYS[AI_SEARCH]


BUDGET_LOGGER = "apps.system_intelligence.services.public_assistant.budget"
