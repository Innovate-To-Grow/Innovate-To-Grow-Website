"""What one member's shares may cost the service: how many, how fast they change, and what listing them loads."""

from django.conf import settings
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from apps.authn.services.account.delete_account import delete_member_account
from apps.projects.models import PastProjectShare
from apps.projects.views.past_project_share import MAX_SHARES_PER_MEMBER

from .share_helpers import Member, PastProjectShareTestCase, sample_payload, sample_row


def _rates(**overrides):
    rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], **overrides}
    return {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}


class PastProjectShareLimitsTests(PastProjectShareTestCase):
    def test_create_is_refused_once_the_member_keeps_the_maximum(self):
        PastProjectShare.objects.bulk_create(
            PastProjectShare(name=f"Share {n}", rows=[sample_row()], created_by=self.member)
            for n in range(MAX_SHARES_PER_MEMBER)
        )

        response = self.client.post("/projects/past-shares/", sample_payload(), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "share_limit_reached")
        self.assertEqual(PastProjectShare.objects.filter(created_by=self.member).count(), MAX_SHARES_PER_MEMBER)

    def test_other_members_shares_do_not_count(self):
        other = Member.objects.create_user(password="OtherPass123!", is_active=True)
        PastProjectShare.objects.bulk_create(
            PastProjectShare(name=f"Share {n}", rows=[sample_row()], created_by=other)
            for n in range(MAX_SHARES_PER_MEMBER)
        )

        response = self.client.post("/projects/past-shares/", sample_payload(), format="json")

        self.assertEqual(response.status_code, 201)

    @override_settings(REST_FRAMEWORK=_rates(past_project_share_update="2/minute"))
    def test_updates_and_deletes_are_throttled_per_member(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)
        statuses = []
        for n in range(3):
            share.refresh_from_db()
            response = self.client.patch(
                f"/projects/past-shares/{share.pk}/", {"note": f"Edit {n}", "version": share.version}, format="json"
            )
            statuses.append(response.status_code)

        self.assertEqual(statuses, [200, 200, 429])
        self.assertEqual(self.client.delete(f"/projects/past-shares/{share.pk}/").status_code, 429)

    @override_settings(REST_FRAMEWORK=_rates(past_project_share_update="1/minute"))
    def test_reading_a_share_is_not_throttled(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)

        statuses = {self.client.get(f"/projects/past-shares/{share.pk}/").status_code for _ in range(3)}

        self.assertEqual(statuses, {200})

    def test_mine_counts_rows_without_loading_them(self):
        PastProjectShare.objects.create(
            name="Big", rows=[sample_row(team_number=f"T{n}") for n in range(7)], created_by=self.member
        )
        PastProjectShare.objects.create(name="Empty rows", rows=[], created_by=self.member)

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/projects/past-shares/mine/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["name"]: row["row_count"] for row in response.data}, {"Big": 7, "Empty rows": 0})
        share_selects = [q["sql"] for q in queries.captured_queries if 'FROM "projects_pastprojectshare"' in q["sql"]]
        self.assertEqual(len(share_selects), 1)
        self.assertNotIn('"projects_pastprojectshare"."rows",', share_selects[0])
        self.assertNotIn('"projects_pastprojectshare"."details_text"', share_selects[0])


class AccountDeletionRemovesSharesTests(PastProjectShareTestCase):
    def test_deleting_an_account_deletes_the_members_shares(self):
        mine = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)
        other = Member.objects.create_user(password="OtherPass123!", is_active=True)
        theirs = PastProjectShare.objects.create(name="Theirs", rows=[sample_row()], created_by=other)

        delete_member_account(member=self.member)

        self.assertFalse(PastProjectShare.objects.filter(pk=mine.pk).exists())
        self.assertTrue(PastProjectShare.objects.filter(pk=theirs.pk).exists())
        self.assertEqual(self.client.get(f"/projects/past-shares/{mine.pk}/").status_code, 404)
