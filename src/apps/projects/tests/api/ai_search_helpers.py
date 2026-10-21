"""Shared fixtures for the AI search tests."""

from unittest.mock import MagicMock

from django.contrib.auth import get_user_model

from apps.projects.models import Project
from apps.system_intelligence.services.public_assistant import (
    FEATURE_AI_SEARCH,
    FEATURE_ASSISTANT,
    global_budget_key,
)

ASSISTANT_GLOBAL_KEY = global_budget_key(FEATURE_ASSISTANT)


BUDGET_LOGGER = "apps.system_intelligence.services.public_assistant.budget"


BUDGET_MESSAGE = "AI search has reached its usage limit for now. Please try again later."


Member = get_user_model()


OUTCOME_TOKENS = 13


SEARCH_GLOBAL_KEY = global_budget_key(FEATURE_AI_SEARCH)


SEARCH_URL = "/projects/past-ai-search/"


SERVICE_AGENT = "apps.projects.services.ai_search.run_tool_free_agent"


VIEW_SEARCH = "apps.projects.views.ai_search.run_past_project_ai_search"


def create_project(semester, **overrides):
    defaults = {
        "project_title": "Solar Sensor Platform",
        "team_number": "101",
        "class_code": "CAP",
        "team_name": "Solar Sensors",
        "organization": "Irrigation District",
        "industry": "Agriculture",
        "abstract": "A solar-powered sensor network for field monitoring.",
        "student_names": "Alex Student",
    }
    defaults.update(overrides)
    return Project.objects.create(semester=semester, **defaults)


def agent_result(project):
    """What the model returns. Also given to mocks that must NOT be called, so a
    regression fails an assertion instead of hanging on an unserialisable MagicMock."""
    return MagicMock(text=f'{{"ids": ["{project.id}"]}}', usage={"totalTokens": 9})
