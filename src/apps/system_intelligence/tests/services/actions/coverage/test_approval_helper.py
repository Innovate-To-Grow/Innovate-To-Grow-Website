import json
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import NewsFeedSource
from apps.system_intelligence.models import SystemIntelligenceActionRequest
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.actions.comparison.text import (
    extract_block_text,
    limit_comparison_text,
)
from apps.system_intelligence.services.actions.engine import utils
from apps.system_intelligence.services.actions.engine.exceptions import ActionRequestError
from apps.system_intelligence.services.actions.requests import approval

from ..support.base import SystemIntelligenceActionBase


# ---------------------------------------------------------------------------
# approval.py
# ---------------------------------------------------------------------------
class ApprovalHelperTests(SystemIntelligenceActionBase):
    def test_safe_error_message_replaces_unknown_exception(self):
        message = approval._safe_error_message(RuntimeError("internal detail"))
        self.assertEqual(message, approval._GENERIC_FAILURE_MESSAGE)

    def test_safe_error_message_passes_through_action_error(self):
        message = approval._safe_error_message(ActionRequestError("user facing"))
        self.assertEqual(message, "user facing")

    def test_sanitize_persisted_message_non_string_returns_generic(self):
        self.assertEqual(approval._sanitize_persisted_message(None), approval._GENERIC_FAILURE_MESSAGE)

    def test_sanitize_strips_control_characters_and_truncates(self):
        cleaned = approval._sanitize_persisted_message("a\x00b\x1fc")
        self.assertEqual(cleaned, "a b c")

    def test_apply_action_unsupported_type_raises(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type="something_unsupported",
            target_app_label="cms",
            target_model="NewsFeedSource",
            target_pk=str(source.pk),
            title="Unsupported",
        )
        with self.assertRaises(ActionRequestError) as cm:
            approval.apply_action(action, self.admin_user)
        self.assertIn("Unsupported action type: something_unsupported", str(cm.exception))

    def test_unknown_exception_persists_generic_failure_message(self):
        # Drive approve_action_request through the except branch with a non-vetted
        # exception so the persisted error_message is the generic string.
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        response = actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {"name": "Renamed"})
        action_id = response["action_request"]["id"]
        with patch(
            "apps.system_intelligence.services.actions.requests.approval.apply_action",
            side_effect=RuntimeError("low level detail"),
        ):
            with self.assertRaises(RuntimeError):
                actions.approve_action_request(action_id, self.admin_user)
        action = SystemIntelligenceActionRequest.objects.get(id=action_id)
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_FAILED)
        self.assertEqual(action.error_message, approval._GENERIC_FAILURE_MESSAGE)


# ---------------------------------------------------------------------------
# utils.py
# ---------------------------------------------------------------------------
class ValidationMessageTests(TestCase):
    def test_message_dict_serialized_as_json(self):
        exc = ValidationError({"title": ["This field is required."]})
        result = utils.validation_message(exc)
        self.assertEqual(json.loads(result), {"title": ["This field is required."]})

    def test_plain_messages_joined(self):
        exc = ValidationError(["First problem.", "Second problem."])
        result = utils.validation_message(exc)
        self.assertEqual(result, "First problem.; Second problem.")


# ---------------------------------------------------------------------------
# comparison/text.py
# ---------------------------------------------------------------------------
class TextHelperTests(TestCase):
    def test_extract_block_text_falls_back_to_json_when_no_text_parts(self):
        # data has no string parts (only numbers) so the text join is empty and
        # the json fallback kicks in.
        block = {"data": {"count": 3, "ratio": 1.5}}
        result = extract_block_text(block)
        self.assertIn('"count": 3', result)

    def test_limit_comparison_text_none_returns_empty_string(self):
        self.assertEqual(limit_comparison_text(None), "")
