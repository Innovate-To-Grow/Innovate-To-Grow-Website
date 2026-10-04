from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.projects.models import Project, Semester
from apps.projects.services.ai_search import (
    find_ai_search_candidates,
    prepare_past_project_ai_search,
    run_past_project_ai_search,
)
from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    PublicAssistantTokenBudget,
    PublicAssistantTokenReservation,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import (
    FEATURE_AI_SEARCH,
    FEATURE_ASSISTANT,
    BudgetBackendUnavailable,
    budget,
    estimate_public_input_tokens,
    global_budget_key,
    global_tokens_used,
    hash_ip,
    issue_visitor_token,
    legacy_actor,
    member_actor,
    record_usage,
    visitor_actor,
)

Member = get_user_model()

SEARCH_URL = "/projects/past-ai-search/"
VIEW_SEARCH = "apps.projects.views.ai_search.run_past_project_ai_search"
SERVICE_AGENT = "apps.projects.services.ai_search.run_tool_free_agent"
BUDGET_LOGGER = "apps.system_intelligence.services.public_assistant.budget"
BUDGET_MESSAGE = "AI search has reached its usage limit for now. Please try again later."
SEARCH_GLOBAL_KEY = global_budget_key(FEATURE_AI_SEARCH)
ASSISTANT_GLOBAL_KEY = global_budget_key(FEATURE_ASSISTANT)


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


class PastProjectAISearchAPIViewTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = Member.objects.create_user(email="member@example.com", password="pw")

        self.config = SystemIntelligenceConfig.objects.create(
            name="AI",
            is_active=True,
            public_assistant_enabled=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            public_assistant_max_message_chars=100,
            public_assistant_ip_token_limit=100_000,
            public_assistant_ip_token_window_seconds=3600,
        )
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKIATEST",
            secret_access_key="secret",
            default_region="us-west-2",
        )

        self.current = Semester.objects.create(year=2025, season=Semester.Season.FALL, is_published=True)
        self.past_spring = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_published=True)
        self.past_fall = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=True)
        self.unpublished = Semester.objects.create(year=2024, season=Semester.Season.SPRING, is_published=False)

        self.current_project = create_project(self.current, project_title="Current Solar Project")
        self.past_project_a = create_project(
            self.past_spring,
            project_title="Solar Sensor Irrigation Network",
            team_number="101",
        )
        self.past_project_b = create_project(
            self.past_fall,
            project_title="Battery Health Monitor",
            team_number="102",
            abstract="Predictive maintenance for solar battery systems.",
        )
        self.unpublished_project = create_project(self.unpublished, project_title="Unpublished Solar Project")

    def authenticate(self):
        self.client.force_authenticate(user=self.member)

    def test_authentication_required(self):
        response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 401)

    def test_blank_query_validation(self):
        self.authenticate()

        response = self.client.post("/projects/past-ai-search/", {"query": "   "}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("query", response.data)

    def test_too_long_query_validation(self):
        self.authenticate()
        self.config.public_assistant_max_message_chars = 5
        self.config.save()

        response = self.client.post("/projects/past-ai-search/", {"query": "too long"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("query", response.data)

    def test_public_assistant_disabled_does_not_disable_ai_search(self):
        self.authenticate()
        self.config.public_assistant_enabled = False
        self.config.save()

        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            return_value={
                "project_ids": [str(self.past_project_a.id)],
                "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
            },
        ) as mocked_search:
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(
            [project["project_title"] for project in response.data["results"]], ["Solar Sensor Irrigation Network"]
        )
        mocked_search.assert_called_once()

    def test_budget_limit_returns_429_without_calling_ai(self):
        self.authenticate()
        self.config.public_assistant_ip_token_limit = 5000
        self.config.save()
        record_usage(member_actor(self.member.pk).key, 5000, 3600)

        # A real return value: if the budget check regressed, the test must fail
        # on the assertions below, not hang serialising a MagicMock.
        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            return_value={"project_ids": [], "usage": {"totalTokens": 1}},
        ) as mocked_search:
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "budget_exceeded")
        # The limit may be the shared global one, so the copy must not blame the member.
        self.assertEqual(response.data["detail"], BUDGET_MESSAGE)
        mocked_search.assert_not_called()
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_BUDGET)

    def test_ai_project_ids_return_serialized_projects_in_ai_order(self):
        self.authenticate()
        invalid_id = "00000000-0000-0000-0000-000000000000"

        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            return_value={
                "project_ids": [
                    str(self.past_project_b.id),
                    str(self.current_project.id),
                    invalid_id,
                    str(self.unpublished_project.id),
                    str(self.past_project_a.id),
                ],
                "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
            },
        ):
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["query"], "solar")
        self.assertEqual(response.data["usage"]["totalTokens"], 13)
        # The newest published semester is included now, so the current project is serialized too
        # (in AI order); only the invalid id and the unpublished project are dropped.
        self.assertEqual(
            [project["project_title"] for project in response.data["results"]],
            ["Battery Health Monitor", "Current Solar Project", "Solar Sensor Irrigation Network"],
        )

    def test_candidate_search_uses_past_project_boundary(self):
        candidates = find_ai_search_candidates("solar")
        titles = {project.project_title for project in candidates}

        self.assertIn("Solar Sensor Irrigation Network", titles)
        self.assertIn("Battery Health Monitor", titles)
        # Every published semester is in scope, including the newest; only unpublished is excluded.
        self.assertIn("Current Solar Project", titles)
        self.assertNotIn("Unpublished Solar Project", titles)

    def test_service_uses_tool_free_agent_and_parses_ids(self):
        result = MagicMock(
            text=f'{{"ids": ["{self.past_project_b.id}", "{self.past_project_a.id}"], "reason": "solar"}}',
            usage={"inputTokens": 8, "outputTokens": 4, "totalTokens": 12},
        )

        with patch("apps.projects.services.ai_search.run_tool_free_agent", return_value=result) as mock_agent:
            outcome = run_past_project_ai_search(query="solar", limit=2, config=self.config)

        self.assertEqual(outcome["project_ids"], [str(self.past_project_b.id), str(self.past_project_a.id)])
        self.assertEqual(outcome["usage"]["totalTokens"], 12)
        mock_agent.assert_called_once()
        self.assertEqual(mock_agent.call_args.kwargs["agent_name"], "past_project_ai_search")

    def test_success_logs_source_user_and_results(self):
        self.authenticate()
        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            return_value={
                "project_ids": [str(self.past_project_a.id)],
                "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
            },
        ):
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        message = AssistantMessageLog.objects.get()
        convo = message.conversation
        self.assertEqual(convo.source, AssistantConversationLog.SOURCE_AI_SEARCH)
        self.assertEqual(convo.user_id, self.member.id)
        self.assertIsNone(convo.session_id)
        self.assertEqual(message.status, AssistantMessageLog.STATUS_OK)
        self.assertEqual(message.prompt, "solar")
        self.assertEqual(
            message.results,
            [{"id": str(self.past_project_a.id), "project_title": "Solar Sensor Irrigation Network"}],
        )

    def test_unavailable_logs_unavailable_row(self):
        self.authenticate()
        self.config.default_model_id = ""
        self.config.public_assistant_model_id = ""
        self.config.save()

        response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_UNAVAILABLE)
        self.assertEqual(message.conversation.user_id, self.member.id)

    def test_error_logs_error_row(self):
        self.authenticate()
        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            side_effect=RuntimeError("boom"),
        ):
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 502)
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_ERROR)

    def test_recorder_failure_does_not_break_response(self):
        self.authenticate()
        with (
            patch(
                "apps.projects.views.ai_search.run_past_project_ai_search",
                return_value={
                    "project_ids": [str(self.past_project_a.id)],
                    "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
                },
            ),
            patch(
                "apps.system_intelligence.services.usage_log.recorder.AssistantMessageLog.objects.create",
                side_effect=RuntimeError("audit down"),
            ),
        ):
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(AssistantMessageLog.objects.count(), 0)


OUTCOME_TOKENS = 13


def agent_result(project):
    """What the model returns. Also given to mocks that must NOT be called, so a
    regression fails an assertion instead of hanging on an unserialisable MagicMock."""
    return MagicMock(text=f'{{"ids": ["{project.id}"]}}', usage={"totalTokens": 9})


# The database path is the production path (no Redis): keep it explicit here.
@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class PastProjectAISearchBudgetTests(TestCase):
    """Token budgets: per MEMBER (never per IP) plus AI search's own global spend ceiling."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = Member.objects.create_user(email="member@example.com", password="pw", is_active=True)
        self.other_member = Member.objects.create_user(email="other@example.com", password="pw", is_active=True)
        self.config = SystemIntelligenceConfig.objects.create(
            name="AI",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            public_assistant_ip_token_window_seconds=3600,
        )
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKIATEST",
            secret_access_key="secret",
            default_region="us-west-2",
        )
        semester = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_published=True)
        self.project = create_project(semester, project_title="Solar Sensor Irrigation Network")
        create_project(semester, project_title="Battery Health Monitor", team_number="102")
        self.outcome = {
            "project_ids": [str(self.project.id)],
            "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": OUTCOME_TOKENS},
        }
        prepared = prepare_past_project_ai_search(query="solar", limit=10, config=self.config)
        # What one search reserves before the model call: estimated prompt + output cap.
        self.reserved = prepared.estimated_input_tokens + prepared.max_tokens
        self.member_key = member_actor(self.member.pk).key
        self.other_key = member_actor(self.other_member.pk).key

    def configure(self, **fields):
        for name, value in fields.items():
            setattr(self.config, name, value)
        self.config.save()

    def search(self, member=None, *, query="solar", ip="169.236.10.10"):
        self.client.force_authenticate(user=member or self.member)
        return self.client.post(SEARCH_URL, {"query": query}, format="json", REMOTE_ADDR=ip)

    def test_search_charges_the_member_and_the_global_budget_not_the_ip(self):
        with patch(VIEW_SEARCH, return_value=self.outcome):
            response = self.search(ip="169.236.10.10")

        self.assertEqual(response.status_code, 200)
        used = dict(PublicAssistantTokenBudget.objects.values_list("pk", "tokens_used"))
        # The member's row and AI search's global row -- not the assistant's.
        self.assertEqual(used, {self.member_key: OUTCOME_TOKENS, SEARCH_GLOBAL_KEY: OUTCOME_TOKENS})
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())
        # The hashed IP is still recorded for audit, but keys no budget.
        self.assertEqual(AssistantConversationLog.objects.get().ip_hash, hash_ip("169.236.10.10"))

    def test_budgets_are_per_member_behind_one_campus_ip(self):
        self.configure(public_assistant_ip_token_limit=self.reserved)
        record_usage(self.member_key, self.reserved, 3600)

        with patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search:
            exhausted = self.search(self.member)
            other = self.search(self.other_member)

        self.assertEqual(exhausted.status_code, 429)
        self.assertEqual(exhausted.data["code"], "budget_exceeded")
        self.assertEqual(other.status_code, 200)
        self.assertTrue(other.data["available"])
        mocked_search.assert_called_once()
        self.assertEqual(budget.tokens_used(self.other_key), OUTCOME_TOKENS)

    def test_exhausted_assistant_buckets_do_not_block_a_member_search(self):
        self.configure(public_assistant_ip_token_limit=self.reserved)
        visitor_key = visitor_actor(issue_visitor_token()).key
        for key in (visitor_key, legacy_actor().key, hash_ip("169.236.10.10")):
            record_usage(key, self.reserved, 3600)

        with patch(VIEW_SEARCH, return_value=self.outcome):
            response = self.search()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])

    def test_exhausted_member_does_not_block_the_anonymous_assistant(self):
        self.configure(public_assistant_ip_token_limit=5000, public_assistant_enabled=True)
        record_usage(self.member_key, 5000, 3600)
        with patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search:
            self.assertEqual(self.search().status_code, 429)
        mocked_search.assert_not_called()
        self.client.force_authenticate(user=None)

        with (
            patch("apps.system_intelligence.views.public_assistant.build_public_context", return_value="ctx"),
            patch(
                "apps.system_intelligence.views.public_assistant.answer_public_question",
                return_value={"text": "hello", "usage": {"totalTokens": 5}},
            ),
        ):
            token = self.client.get("/assistant/config/").data["visitor_token"]
            response = self.client.post(
                "/assistant/chat/",
                {"message": "hi", "visitor_token": token},
                format="json",
                REMOTE_ADDR="169.236.10.10",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])

    def test_search_cannot_overshoot_a_nearly_spent_budget(self):
        # Old behaviour: "used < limit" admitted the search, then its whole cost
        # was recorded on top (49,999 + one search = 64,699).
        limit = self.reserved + 500
        self.configure(public_assistant_ip_token_limit=limit)
        record_usage(self.member_key, limit - 1, 3600)

        with patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent:
            response = self.search()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "budget_exceeded")
        mock_agent.assert_not_called()
        self.assertEqual(budget.tokens_used(self.member_key), limit - 1)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 0)

    def test_budget_is_reserved_before_the_model_call_and_reconciled_after(self):
        seen = {}

        def agent(**_kwargs):
            seen["member"] = budget.tokens_used(self.member_key)
            seen["global"] = global_tokens_used(FEATURE_AI_SEARCH)
            seen["reservations"] = PublicAssistantTokenReservation.objects.count()
            return MagicMock(
                text=f'{{"ids": ["{self.project.id}"]}}',
                usage={"inputTokens": 200, "outputTokens": 20, "totalTokens": 220},
            )

        with patch(SERVICE_AGENT, side_effect=agent) as mock_agent:
            response = self.search()

        self.assertEqual(response.status_code, 200)
        mock_agent.assert_called_once()
        self.assertEqual(seen, {"member": self.reserved, "global": self.reserved, "reservations": 2})
        # The reservation covers the output cap the model was actually given.
        self.assertEqual(mock_agent.call_args.kwargs["max_tokens"], 700)
        self.assertGreater(self.reserved, 700)
        self.assertEqual(budget.tokens_used(self.member_key), 220)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 220)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_member_can_search_until_the_reservation_no_longer_fits(self):
        self.configure(public_assistant_ip_token_limit=self.reserved + OUTCOME_TOKENS)

        with patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search:
            statuses = [self.search().status_code for _ in range(3)]

        self.assertEqual(statuses, [200, 200, 429])
        self.assertEqual(mocked_search.call_count, 2)
        self.assertLessEqual(budget.tokens_used(self.member_key), self.reserved + OUTCOME_TOKENS)

    def test_exhausted_global_budget_blocks_every_member_with_the_budget_message(self):
        self.configure(public_assistant_global_token_limit=self.reserved)
        record_usage(SEARCH_GLOBAL_KEY, 1, 86400)

        with (
            patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search,
            self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs,
        ):
            responses = [self.search(self.member), self.search(self.other_member)]

        self.assertIn("global token budget exhausted for AI search", logs.output[0])

        for response in responses:
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.data["code"], "budget_exceeded")
            self.assertEqual(response.data["detail"], BUDGET_MESSAGE)
        mocked_search.assert_not_called()
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 1)
        self.assertFalse(PublicAssistantTokenBudget.objects.exclude(pk=SEARCH_GLOBAL_KEY).exists())

    def _chat_reserved(self):
        """What one public-assistant turn reserves before its model call."""
        return (
            estimate_public_input_tokens(message="hi", history=[], config=self.config, context="ctx")
            + self.config.public_assistant_max_response_tokens
        )

    def _anonymous_chat(self, *, minted_identities):
        """Chat turns the way an anonymous script sends them: a freshly minted identity each time."""
        self.client.force_authenticate(user=None)
        statuses = []
        with (
            patch("apps.system_intelligence.views.public_assistant.build_public_context", return_value="ctx"),
            patch(
                "apps.system_intelligence.views.public_assistant.answer_public_question",
                return_value={"text": "hello", "usage": {"totalTokens": 5}},
            ) as mock_answer,
        ):
            for _ in range(minted_identities):
                token = self.client.get("/assistant/config/").data["visitor_token"]
                response = self.client.post(
                    "/assistant/chat/",
                    {"message": "hi", "visitor_token": token},
                    format="json",
                    REMOTE_ADDR="198.51.100.7",
                )
                statuses.append(response.status_code)
        return statuses, mock_answer.call_count

    def test_draining_the_assistant_with_minted_identities_does_not_pause_member_search(self):
        # The global limit is ONE number, but each feature has its own counter.
        # Room for exactly three chat turns (5 tokens each after reconciling).
        chat_reserved = self._chat_reserved()
        self.assertLess(self.reserved + OUTCOME_TOKENS, chat_reserved)
        self.configure(public_assistant_global_token_limit=chat_reserved + 10, public_assistant_enabled=True)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            statuses, model_calls = self._anonymous_chat(minted_identities=6)

        # Every request was a brand-new visitor, so no per-visitor limit bound:
        # the assistant's global budget is what stopped the script.
        self.assertEqual(statuses, [200, 200, 200, 429, 429, 429])
        self.assertEqual(model_calls, 3)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("global token budget exhausted for Public assistant", logs.output[0])
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 15)

        # Members' AI search is untouched by it: same limit, separate counter.
        with (
            patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search,
            self.assertNoLogs(BUDGET_LOGGER, level="WARNING"),
        ):
            responses = [self.search(self.member), self.search(self.other_member)]

        for response in responses:
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["available"])
        self.assertEqual(mocked_search.call_count, 2)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 2 * OUTCOME_TOKENS)
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 15)

    def test_spent_search_budget_does_not_pause_the_public_assistant(self):
        chat_reserved = self._chat_reserved()
        self.configure(public_assistant_global_token_limit=chat_reserved, public_assistant_enabled=True)
        record_usage(SEARCH_GLOBAL_KEY, chat_reserved, 86400)

        with (
            patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search,
            self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs,
        ):
            refused = self.search()
        self.assertEqual(refused.status_code, 429)
        self.assertEqual(refused.data["code"], "budget_exceeded")
        mocked_search.assert_not_called()
        self.assertIn("global token budget exhausted for AI search", logs.output[0])

        with self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
            statuses, model_calls = self._anonymous_chat(minted_identities=1)

        self.assertEqual((statuses, model_calls), ([200], 1))
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 5)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), chat_reserved)

    def test_a_spent_assistant_budget_row_is_not_what_search_is_checked_against(self):
        # The assistant's row is far over the limit; a search still fits its own.
        self.configure(public_assistant_global_token_limit=self.reserved)
        record_usage(ASSISTANT_GLOBAL_KEY, 10 * self.reserved, 86400)

        with patch(VIEW_SEARCH, return_value=self.outcome):
            response = self.search()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), OUTCOME_TOKENS)
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 10 * self.reserved)

    def test_unparsable_provider_usage_is_answered_and_settled_at_the_reservation(self):
        outcome = {"project_ids": [str(self.project.id)], "usage": {"totalTokens": "n/a"}}

        with (
            patch(VIEW_SEARCH, return_value=outcome),
            self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs,
        ):
            response = self.search()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual([row["id"] for row in response.data["results"]], [str(self.project.id)])
        self.assertIn("Unparsable provider token usage", logs.output[0])
        self.assertEqual(budget.tokens_used(self.member_key), self.reserved)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), self.reserved)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_a_usage_block_that_is_not_plain_integers_is_never_echoed_or_a_500(self):
        odd_blocks = (
            {"inputTokens": float("nan"), "outputTokens": float("inf"), "totalTokens": float("nan")},
            {"inputTokens": 5, "outputTokens": 7, "totalTokens": 10**30},
            ["not", "a", "mapping"],
        )
        for usage in odd_blocks:
            with self.subTest(usage=repr(usage)[:60]):
                PublicAssistantTokenBudget.objects.all().delete()
                PublicAssistantTokenReservation.objects.all().delete()
                outcome = {"project_ids": [str(self.project.id)], "usage": usage}

                with patch(VIEW_SEARCH, return_value=outcome), self.assertLogs(BUDGET_LOGGER, level="WARNING"):
                    response = self.search()

                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.data["results"]], [str(self.project.id)])
                for value in response.data["usage"].values():
                    self.assertIs(type(value), int)
                    self.assertLessEqual(value, budget.MAX_REPORTED_TOKENS)
                # Unreadable usage is charged as reserved, never as nothing, and the reservation is consumed.
                self.assertEqual(budget.tokens_used(self.member_key), self.reserved)
                self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), self.reserved)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_zero_global_limit_switches_the_model_call_off(self):
        self.configure(public_assistant_global_token_limit=0)

        with patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent:
            response = self.search()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "budget_exceeded")
        mock_agent.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_provider_error_releases_the_member_and_global_reservations(self):
        self.configure(public_assistant_global_token_limit=self.reserved)

        with patch(SERVICE_AGENT, side_effect=RuntimeError("bedrock down")):
            statuses = [self.search().status_code for _ in range(3)]

        # Nothing leaked: three failures in a row still fit a budget of one search.
        self.assertEqual(statuses, [502, 502, 502])
        self.assertEqual(budget.tokens_used(self.member_key), 0)
        self.assertEqual(global_tokens_used(FEATURE_AI_SEARCH), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

        with patch(VIEW_SEARCH, return_value=self.outcome):
            self.assertEqual(self.search().status_code, 200)

    def test_query_without_candidates_spends_nothing_and_skips_the_model(self):
        self.configure(public_assistant_global_token_limit=0)

        with patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent:
            response = self.search(query="zzzzzz")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["results"], [])
        self.assertEqual(response.data["usage"]["totalTokens"], 0)
        mock_agent.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())
        self.assertEqual(AssistantMessageLog.objects.get().status, AssistantMessageLog.STATUS_OK)

    def test_budget_backend_failure_is_a_503_never_a_500(self):
        with (
            patch(
                "apps.projects.views.ai_search.reserve_budget",
                side_effect=BudgetBackendUnavailable("db down"),
            ),
            patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent,
        ):
            response = self.search()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "budget_unavailable")
        mock_agent.assert_not_called()

    def test_preparation_failure_is_a_502_and_spends_nothing(self):
        with (
            patch(
                "apps.projects.views.ai_search.prepare_past_project_ai_search",
                side_effect=RuntimeError("candidate query failed"),
            ),
            patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent,
        ):
            response = self.search()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "ai_search_error")
        mock_agent.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())
        self.assertEqual(AssistantMessageLog.objects.get().status, AssistantMessageLog.STATUS_ERROR)

    def test_reconcile_failure_does_not_break_the_response(self):
        with (
            patch(VIEW_SEARCH, return_value=self.outcome),
            patch(
                "apps.projects.views.ai_search.reconcile_budget",
                side_effect=BudgetBackendUnavailable("db blip"),
            ),
        ):
            response = self.search()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])

    def test_release_failure_still_answers_502(self):
        with (
            patch(VIEW_SEARCH, side_effect=RuntimeError("bedrock down")),
            patch(
                "apps.projects.views.ai_search.release_budget",
                side_effect=BudgetBackendUnavailable("db blip"),
            ),
        ):
            response = self.search()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "ai_search_error")


class PreparePastProjectAISearchTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.config = SystemIntelligenceConfig.objects.create(
            name="AI",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        semester = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_published=True)
        self.project = create_project(semester, project_title="Solar Sensor Irrigation Network")

    def test_prepare_returns_none_without_candidates(self):
        self.assertIsNone(prepare_past_project_ai_search(query="zzzzzz", limit=5, config=self.config))

    def test_prepare_estimates_the_whole_prompt_and_caps_output(self):
        prepared = prepare_past_project_ai_search(query="solar", limit=50, config=self.config)

        self.assertEqual(prepared.limit, 10)
        self.assertIn(str(self.project.id), prepared.prompt)
        self.assertEqual(prepared.max_tokens, 700)
        # At least the 4-characters-per-token floor over system text + prompt.
        self.assertGreaterEqual(
            prepared.estimated_input_tokens,
            (len(prepared.system_text) + len(prepared.prompt)) // 4,
        )

    def test_estimate_charges_non_ascii_text_conservatively(self):
        ascii_only = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)
        self.project.abstract = "太阳能传感器网络" * 20
        self.project.save()

        with_cjk = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)

        # 160 CJK characters are 480 UTF-8 bytes: charged one token per byte.
        self.assertGreater(with_cjk.estimated_input_tokens, ascii_only.estimated_input_tokens + 400)

    def test_output_cap_follows_a_smaller_configured_response_limit(self):
        self.config.public_assistant_max_response_tokens = 200

        prepared = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)

        self.assertEqual(prepared.max_tokens, 200)

    def test_run_reuses_a_prepared_prompt_without_searching_again(self):
        prepared = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)
        result = MagicMock(text=f'{{"ids": ["{self.project.id}"]}}', usage={"totalTokens": 9})

        with (
            patch(SERVICE_AGENT, return_value=result) as mock_agent,
            patch("apps.projects.services.ai_search.find_ai_search_candidates") as mock_candidates,
        ):
            outcome = run_past_project_ai_search(query="solar", limit=5, config=self.config, prepared=prepared)

        mock_candidates.assert_not_called()
        self.assertEqual(outcome["project_ids"], [str(self.project.id)])
        self.assertEqual(mock_agent.call_args.kwargs["input_data"], prepared.prompt)
        self.assertEqual(mock_agent.call_args.kwargs["system_text"], prepared.system_text)
        self.assertEqual(mock_agent.call_args.kwargs["max_tokens"], prepared.max_tokens)

    def test_run_without_candidates_returns_empty_without_a_model_call(self):
        with patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent:
            outcome = run_past_project_ai_search(query="zzzzzz", limit=5, config=self.config)

        mock_agent.assert_not_called()
        self.assertEqual(outcome, {"project_ids": [], "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}})
