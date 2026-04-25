from authn.models import Member
from cms.models import CMSPage, NewsFeedSource
from core.models.base.system_intelligence import SystemIntelligenceActionRequest
from core.services import system_intelligence_actions as actions

from .base import SystemIntelligenceActionBase


class SystemIntelligenceDBActionTests(SystemIntelligenceActionBase):
    def test_db_update_proposal_is_single_record_and_requires_approval(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml", is_active=True
        )
        response = actions.propose_db_update(
            "cms",
            "NewsFeedSource",
            str(source.pk),
            {"name": "Updated Source", "is_active": False},
            summary="Update source display name.",
        )
        source.refresh_from_db()
        self.assertEqual(source.name, "UC Merced")
        action = actions.approve_action_request(response["action_request"]["id"], self.admin_user)
        source.refresh_from_db()
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_APPLIED)
        self.assertEqual(source.name, "Updated Source")
        self.assertFalse(source.is_active)
        self.assertEqual(response["action_request"]["comparison"], {})

    def test_db_create_and_delete_proposals_apply_after_approval(self):
        create_response = actions.propose_db_create(
            "cms",
            "NewsFeedSource",
            {"name": "New Feed", "source_key": "new-feed", "feed_url": "https://example.com/new.xml"},
        )
        self.assertFalse(NewsFeedSource.objects.filter(source_key="new-feed").exists())
        create_action = actions.approve_action_request(create_response["action_request"]["id"], self.admin_user)
        created = NewsFeedSource.objects.get(source_key="new-feed")
        self.assertEqual(create_action.target_pk, str(created.pk))
        delete_response = actions.propose_db_delete("cms", "NewsFeedSource", str(created.pk))
        actions.approve_action_request(delete_response["action_request"]["id"], self.admin_user)
        self.assertFalse(NewsFeedSource.objects.filter(pk=created.pk).exists())

    def test_db_write_rejects_sensitive_fields_and_cms_page_bypass(self):
        member = Member.objects.create_user(password="testpass123")
        with self.assertRaises(actions.ActionRequestError):
            actions.propose_db_update("authn", "Member", str(member.pk), {"password": "new-pass"})
        page = CMSPage.objects.create(slug="home", route="/home", title="Home", status="draft")
        with self.assertRaises(actions.ActionRequestError):
            actions.propose_db_update("cms", "CMSPage", str(page.pk), {"title": "Bypass Preview"})

    def test_reject_action_does_not_mutate_record(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml", is_active=True
        )
        response = actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {"name": "Rejected"})
        action = actions.reject_action_request(response["action_request"]["id"], self.admin_user)
        source.refresh_from_db()
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_REJECTED)
        self.assertEqual(source.name, "UC Merced")

    def test_approve_fails_when_target_changed_after_proposal(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml", is_active=True
        )
        response = actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {"name": "Approved"})
        source.name = "Changed elsewhere"
        source.save()
        with self.assertRaises(actions.ActionRequestError):
            actions.approve_action_request(response["action_request"]["id"], self.admin_user)
        source.refresh_from_db()
        action = SystemIntelligenceActionRequest.objects.get(id=response["action_request"]["id"])
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_FAILED)
        self.assertEqual(source.name, "Changed elsewhere")
