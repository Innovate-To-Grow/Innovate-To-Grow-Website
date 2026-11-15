from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.services.email_monitoring.helpers import monitoring_settings
from apps.mail.models import BouncedAddress
from apps.mail.services.email_monitoring.addresses import aggregate
from apps.mail.tests.services.bounced_addresses.aggregate.test_aggregate import Status

from ..helpers import count_now, make_bounce, make_person, make_row, settled


class RebuildAndRefreshTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_rebuild_recounts_stored_records_and_keeps_review_and_suppression(self):
        make_bounce(recipient="r@example.org", match_method="message_id")
        make_bounce(recipient="r@example.org", classification="soft", status_code="5.2.2")
        count_now()
        stamp = timezone.now()
        BouncedAddress.objects.filter(address="r@example.org").update(
            status=Status.DISMISSED, reviewed_at=stamp, suppressed_at=stamp, suppression="suppressed", hard_count=99
        )

        aggregate.rebuild()
        count_now()

        row = BouncedAddress.objects.get(address="r@example.org")
        self.assertEqual((row.hard_count, row.soft_count, row.matched_count), (1, 1, 1))
        self.assertEqual(row.status, Status.DISMISSED)
        self.assertEqual(row.suppressed_at, stamp)

    def test_refresh_all_follows_contact_changes_made_elsewhere(self):
        make_bounce(recipient="moved@example.org")
        count_now()
        self.assertEqual(BouncedAddress.objects.get(address="moved@example.org").role, BouncedAddress.Role.NONE)
        member = make_person("moved@example.org")

        changed = aggregate.refresh_all()

        row = BouncedAddress.objects.get(address="moved@example.org")
        self.assertEqual(changed, 1)
        self.assertEqual((row.role, row.member_id), (BouncedAddress.Role.PRIMARY, member.pk))

    def test_each_refresh_run_covers_at_most_its_share_and_continues_where_it_stopped(self):
        rows = [make_row(f"r{index}@example.org") for index in range(3)]
        for row in rows:
            make_person(row.address)
        order = [row.address for row in sorted(rows, key=lambda row: row.pk)]

        with monitoring_settings(address_refresh_rows_per_run=2, address_batch_size=1):
            first = aggregate.refresh_all()
            refreshed_first = set(BouncedAddress.objects.filter(role="primary").values_list("address", flat=True))
            second = aggregate.refresh_all()
            third = aggregate.refresh_all()

        self.assertEqual((first, second, third), (2, 1, 0))
        self.assertEqual(refreshed_first, set(order[:2]))
        self.assertEqual(BouncedAddress.objects.filter(role="primary").count(), 3)

    def test_a_stop_request_ends_the_runs(self):
        make_bounce(recipient="s@example.org")

        with settled():
            result = aggregate.run(should_stop=lambda: True)

        self.assertEqual(result["graph"], 0)
        self.assertEqual(aggregate.refresh_all(should_stop=lambda: True), 0)
