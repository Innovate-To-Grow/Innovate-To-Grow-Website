from django.core.exceptions import PermissionDenied
from django.test import TestCase

from apps.authn.models import Member
from apps.cms.models import NewsFeedSource
from apps.event.tests.helpers import make_admin
from apps.system_intelligence.models import SystemIntelligenceActionRequest
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.actions.comparison import builders
from apps.system_intelligence.services.actions.engine.exceptions import ActionRequestError
from apps.system_intelligence.services.actions.orm import records as orm_records

from ..support.base import SystemIntelligenceActionBase


# ---------------------------------------------------------------------------
# orm/records.py
# ---------------------------------------------------------------------------
class OrmRecordsTests(TestCase):
    def test_get_object_missing_raises(self):
        valid_uuid = "11111111-1111-1111-1111-111111111111"
        with self.assertRaises(ActionRequestError) as cm:
            orm_records.get_object(NewsFeedSource, valid_uuid)
        self.assertIn("was not found", str(cm.exception))

    def test_get_object_invalid_pk_raises(self):
        with self.assertRaises(ActionRequestError) as cm:
            orm_records.get_object(NewsFeedSource, "not-a-uuid")
        self.assertIn("Invalid primary key", str(cm.exception))

    def test_check_model_permission_requires_staff(self):
        member = Member.objects.create_user(password="testpass123")
        with self.assertRaises(PermissionDenied) as cm:
            orm_records.check_model_permission(member, NewsFeedSource, "view")
        self.assertIn("Staff authentication is required", str(cm.exception))

    def test_check_model_permission_allows_any_admin(self):
        admin = make_admin(email="cms-orm@example.com")
        orm_records.check_model_permission(admin, NewsFeedSource, "change")

    def test_check_model_permission_denies_an_inactive_admin(self):
        admin = make_admin(email="inactive-orm@example.com", is_active=False)
        with self.assertRaises(PermissionDenied) as cm:
            orm_records.check_model_permission(admin, NewsFeedSource, "change")
        self.assertIn("Staff authentication is required", str(cm.exception))


# ---------------------------------------------------------------------------
# comparison/builders.py
# ---------------------------------------------------------------------------
class BuildersTests(TestCase):
    def test_compact_diff_value_summarizes_large_dict(self):
        big = {f"key{i}": "v" * 50 for i in range(20)}
        result = builders.compact_diff_value(big)
        self.assertIn("summary", result)
        self.assertTrue(result["summary"].endswith("..."))
        self.assertEqual(len(result["summary"]), 403)

    def test_block_key_uses_fallback_when_sort_order_not_int(self):
        key = builders.block_key({"sort_order": "abc", "block_type": "rich_text"}, 4)
        self.assertEqual(key, (4, "rich_text", 4))


# ---------------------------------------------------------------------------
# db/actions.py
# ---------------------------------------------------------------------------
class DbActionGuardTests(SystemIntelligenceActionBase):
    def test_propose_db_create_requires_non_empty_fields(self):
        with self.assertRaises(ActionRequestError) as cm:
            actions.propose_db_create("cms", "NewsFeedSource", {})
        self.assertIn("fields must be a non-empty object", str(cm.exception))

    def test_propose_db_update_requires_non_empty_changes(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        with self.assertRaises(ActionRequestError) as cm:
            actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {})
        self.assertIn("changes must be a non-empty object", str(cm.exception))

    def test_apply_db_create_rejects_non_dict_fields(self):
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_CREATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            title="Bad create",
            payload={"fields": "not a dict"},
        )
        from apps.system_intelligence.services.actions.db.actions import apply_db_create

        with self.assertRaises(ActionRequestError) as cm:
            apply_db_create(action, NewsFeedSource)
        self.assertIn("Invalid create payload", str(cm.exception))

    def test_apply_db_update_rejects_non_dict_changes(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        before = orm_records.serialize_model_instance(source, write=True)
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            target_pk=str(source.pk),
            title="Bad update",
            payload={"changes": "not a dict"},
            before_snapshot=before,
        )
        from apps.system_intelligence.services.actions.db.actions import apply_db_update

        with self.assertRaises(ActionRequestError) as cm:
            apply_db_update(action, NewsFeedSource)
        self.assertIn("Invalid update payload", str(cm.exception))
