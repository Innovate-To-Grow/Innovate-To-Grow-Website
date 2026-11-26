"""The assistant's record writes can't mint a CLI session, take another admin's export, erase the CLI audit trail or
queue background jobs.

Each of these tables was writable by a proposed record write, approved by its own proposer with only the model
permission checked, while its admin is read-only (or, for exports, private to their owner):

* ``cli_admin.CliAuthorizationCode``: the token exchange issues a bearer token for whichever member a code names, so a
  an Admin re-pointing their own code got a CLI session as another Admin;
* ``system_intelligence.SystemIntelligenceExport``: the download authorizes on ``created_by``;
* ``cli_admin.CliAuditLog``: the trail of every CLI write;
* ``core.BackgroundJob``: the worker runs whatever kind and payload a row names.
"""

import json
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cli_admin.models import CliAccessToken, CliAuditLog
from apps.cli_admin.tests.helpers import VALID_REDIRECT_URI, challenge_for, issue_code
from apps.core.models import BackgroundJob
from apps.event.tests.helpers import make_admin, make_superuser
from apps.system_intelligence.models import ChatConversation, SystemIntelligenceActionRequest, SystemIntelligenceExport
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.actions.orm import serialize_model_instance

from .test_authn_write_guard import acting_as

Action = SystemIntelligenceActionRequest
TOKEN_URL = "/admin-api/oauth/token/"


class SystemWriteGuardTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.other_admin = make_superuser(email="other-admin@example.com")

    @staticmethod
    def stored_update(user, obj, changes):
        """A pending update as an earlier proposal would have stored it (before these tables were denied)."""
        return Action.objects.create(
            conversation=ChatConversation.objects.create(created_by=user),
            created_by=user,
            action_type=Action.ACTION_DB_UPDATE,
            target_app_label=obj._meta.app_label,
            target_model=obj._meta.object_name,
            target_pk=str(obj.pk),
            payload={"changes": changes},
            before_snapshot=serialize_model_instance(obj, write=True),
        )

    def assert_refused(self, error, label):
        self.assertEqual(str(error.exception), f"Write access is not allowed for {label}.")


class CliAuthorizationCodeTests(SystemWriteGuardTestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        self.admin = make_admin(email="admin@example.com")
        self.verifier = "verifier-" + "a" * 40
        self.code, self.raw_code = issue_code(self.admin, challenge=challenge_for(self.verifier))

    def exchange(self):
        return self.client.post(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "code": self.raw_code,
                "code_verifier": self.verifier,
                "redirect_uri": VALID_REDIRECT_URI,
                "client_id": "i2g-admin-cli",
            },
            content_type="application/json",
        )

    def test_a_code_cannot_be_re_pointed_to_another_admin(self):
        with acting_as(self.admin):
            with self.assertRaises(actions.ActionRequestError) as error:
                actions.propose_db_update(
                    "cli_admin", "CliAuthorizationCode", str(self.code.pk), {"member_id": str(self.other_admin.pk)}
                )
            with self.assertRaises(actions.ActionRequestError) as read:
                actions.get_record("cli_admin", "CliAuthorizationCode", str(self.code.pk))

        self.assert_refused(error, "cli_admin.CliAuthorizationCode")
        self.assertEqual(str(read.exception), "Read access is not allowed for cli_admin.CliAuthorizationCode.")
        response = self.exchange()
        self.assertEqual(response.status_code, 200)
        token = CliAccessToken.objects.get(token_hash=CliAccessToken.hash_token(response.json()["access_token"]))
        self.assertEqual(token.member, self.admin)

    def test_a_stored_re_point_fails_at_approval_and_cannot_revive_a_used_code(self):
        # The stored change also revives a spent, expired code: the exchange must still refuse it.
        CliAccessToken.objects.all().delete()
        self.code.try_mark_used()
        changes = {
            "member_id": str(self.other_admin.pk),
            "is_used": False,
            "used_at": None,
            "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
        }
        action = self.stored_update(self.admin, self.code, changes)

        with self.assertRaises(actions.ActionRequestError) as error:
            actions.approve_action_request(action.pk, self.admin)

        self.assert_refused(error, "cli_admin.CliAuthorizationCode")
        action.refresh_from_db()
        self.code.refresh_from_db()
        self.assertEqual(action.status, Action.STATUS_FAILED)
        self.assertEqual((self.code.member_id, self.code.is_used), (self.admin.pk, True))
        self.assertEqual(self.exchange().status_code, 400)
        self.assertFalse(CliAccessToken.objects.exists())


class CliAuditLogTests(SystemWriteGuardTestCase):
    def test_audit_rows_can_be_read_but_not_edited_or_deleted(self):
        admin = make_admin(email="admin@example.com")
        entry = CliAuditLog.objects.create(
            actor=admin, action="update", status="success", app_label="cms", model_name="Menu", target_pk="1"
        )
        with acting_as(admin):
            with self.assertRaises(actions.ActionRequestError) as deleted:
                actions.propose_db_delete("cli_admin", "CliAuditLog", str(entry.pk))
            with self.assertRaises(actions.ActionRequestError) as edited:
                actions.propose_db_update("cli_admin", "CliAuditLog", str(entry.pk), {"actor_id": None})
            record = json.loads(actions.get_record("cli_admin", "CliAuditLog", str(entry.pk)))

        for error in (deleted, edited):
            self.assert_refused(error, "cli_admin.CliAuditLog")
        entry.refresh_from_db()
        self.assertEqual(entry.actor, admin)
        self.assertEqual(record["model_name"], "Menu")


class ExportTests(SystemWriteGuardTestCase):
    def test_another_admins_export_cannot_be_taken_over(self):
        admin = make_admin(email="admin@example.com")
        export = SystemIntelligenceExport.objects.create(
            conversation=ChatConversation.objects.create(created_by=self.other_admin),
            created_by=self.other_admin,
            title="Members",
            filename="members.xlsx",
            file="system_intelligence/exports/members.xlsx",
        )
        with acting_as(admin), self.assertRaises(actions.ActionRequestError) as error:
            actions.propose_db_update(
                "system_intelligence", "SystemIntelligenceExport", str(export.pk), {"created_by_id": str(admin.pk)}
            )
        action = self.stored_update(admin, export, {"created_by_id": str(admin.pk)})
        with self.assertRaises(actions.ActionRequestError):
            actions.approve_action_request(action.pk, admin)

        self.assert_refused(error, "system_intelligence.SystemIntelligenceExport")
        export.refresh_from_db()
        self.assertEqual(export.created_by, self.other_admin)
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:system_intelligence_export_download", args=[export.pk]))
        self.assertEqual(response.status_code, 404)


class BackgroundJobTests(SystemWriteGuardTestCase):
    def test_jobs_can_be_read_but_not_queued_or_rewritten(self):
        admin = make_admin(email="admin@example.com")
        failed = BackgroundJob.objects.create(
            kind="authn.member_sheet_sync", dedupe_key="sheet", status=BackgroundJob.Status.FAILED
        )
        notification = {
            "kind": "authn.notification_email",
            "dedupe_key": "any",
            "payload": {"recipient": "someone@example.com", "subject": "Hello", "template": "any"},
        }
        with acting_as(admin):
            with self.assertRaises(actions.ActionRequestError) as queued:
                actions.propose_db_create("core", "BackgroundJob", notification)
            with self.assertRaises(actions.ActionRequestError) as retried:
                actions.propose_db_update("core", "BackgroundJob", str(failed.pk), {"status": "pending"})
            record = json.loads(actions.get_record("core", "BackgroundJob", str(failed.pk)))

        for error in (queued, retried):
            self.assert_refused(error, "core.BackgroundJob")
        failed.refresh_from_db()
        self.assertEqual(failed.status, BackgroundJob.Status.FAILED)
        self.assertEqual(BackgroundJob.objects.count(), 1)
        self.assertEqual(record["kind"], "authn.member_sheet_sync")
