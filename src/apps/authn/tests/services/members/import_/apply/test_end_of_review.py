from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.utils import timezone

from apps.authn.models import Member, MemberImportBatch
from apps.authn.services.members.import_.review import discard_batch
from apps.authn.services.members.import_.review.staging.batches import is_expired, mark_expired, repeat_uploads
from apps.authn.tests.services.members.import_.apply.test_purge import PurgeTestCase, Status
from apps.authn.tests.services.members.import_.helpers import row


class EndOfReviewTests(PurgeTestCase):
    def setUp(self):
        super().setUp()
        self.admin = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Admin")

    def test_discarding_clears_the_password_and_records_who(self):
        batch = self.stage([row("new@example.com")], self.admin, password="Default123!")
        self.assertTrue(check_password("Default123!", batch.default_password_hash))

        discard_batch(batch, self.admin)

        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.default_password_hash), ("discarded", ""))
        self.assertEqual((batch.activity[-1]["action"], batch.activity[-1]["by"]), ("discard", str(self.admin.pk)))

    def test_an_applied_batch_cannot_be_discarded(self):
        batch = self.batch(Status.APPLIED, applied_ago=timedelta(days=1))

        discard_batch(batch, self.admin)

        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.activity), ("applied", []))

    def test_a_review_past_its_lifetime_is_expired(self):
        batch = self.stage([row("new@example.com")], self.admin, password="Default123!")
        self.assertFalse(is_expired(batch))
        mark_expired(batch)
        self.assertEqual(batch.status, "review")

        MemberImportBatch.objects.filter(pk=batch.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        batch.refresh_from_db()
        self.assertTrue(is_expired(batch))
        mark_expired(batch)

        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.default_password_hash), ("expired", ""))
        self.assertTrue(is_expired(batch))

    def test_an_import_applied_after_the_page_read_it_is_not_marked_expired(self):
        """A view read the batch in review past its lifetime; an apply that started before then committed since."""
        read_by_the_view = self.batch(expires_in=-timedelta(minutes=1))
        MemberImportBatch.objects.filter(pk=read_by_the_view.pk).update(status=Status.APPLIED, applied_at=self.now)

        mark_expired(read_by_the_view)

        self.assertEqual(MemberImportBatch.objects.get(pk=read_by_the_view.pk).status, "applied")
        self.assertEqual(read_by_the_view.status, "applied")

    def test_repeat_uploads_of_the_same_file(self):
        sha = "a" * 64
        in_review = self.batch(sha=sha)
        recently_applied = self.batch(Status.APPLIED, applied_ago=timedelta(days=10), sha=sha)
        self.batch(expires_in=-timedelta(minutes=1), sha=sha)
        self.batch(Status.APPLIED, applied_ago=timedelta(days=31), sha=sha)
        self.batch(Status.DISCARDED, sha=sha)
        self.batch()

        self.assertEqual({batch.pk for batch in repeat_uploads(sha)}, {in_review.pk, recently_applied.pk})
        self.assertEqual([batch.pk for batch in repeat_uploads(sha, exclude=in_review.pk)], [recently_applied.pk])
