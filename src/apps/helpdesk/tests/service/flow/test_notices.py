"""Assignment notices end to end: never queued for automated mail, spam or a merged ticket, nor for an inactive
group. When the job runs it judges everything again (the notify switch, shadow mode, the ticket, and whether each
recipient is still one it is meant for: the current assignee, or a member of the current active group who is still an
active Admin), and the timeline records a notice only once it went out. An outsider's link never reaches a notice.
No provider is reached: the email facade's ``deliver_email`` is patched."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import Member
from apps.core.models import BackgroundJob

from ....models import AssignmentGroup, HelpdeskSettings, Ticket, TicketEvent
from ....services import tickets
from ....services.outbound import compose, jobs, notifications
from ....services.tickets import events
from ...helpers import helpdesk_staff, make_admin
from ...helpers.service import Status, new_ticket, sending_settings
from ..outbound.test_jobs import DELIVER, claimed, delivered

Kind = TicketEvent.Kind
DO_NOT_REPLY = (
    "This is an automatic notice: please do not reply to it (a reply would open a new ticket). Work on the ticket "
    "in the admin.\n"
)


class NoticeFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        sending_settings()
        self.lead = helpdesk_staff("lead@example.com")
        self.kim = make_admin(email="kim@example.com", first_name="Kim", last_name="Lee")
        self.ticket = new_ticket(subject="Judging")

    def update(self, ticket=None, **changes):
        with self.captureOnCommitCallbacks(execute=True):
            tickets.update_ticket(ticket or self.ticket, actor=self.lead, **changes)

    def claim_queued(self):
        return [claimed(job) for job in BackgroundJob.objects.filter(kind=jobs.NOTIFY_JOB_KIND).order_by("created_at")]

    def send(self, queued):
        """Run the notice jobs ``queued``; the emails that went out."""
        with patch(DELIVER, side_effect=delivered) as deliver:
            for job in queued:
                notifications.notify_staff_job(job)
        return [call.args[0] for call in deliver.call_args_list]

    def notified(self, ticket=None):
        return list((ticket or self.ticket).events.filter(kind=Kind.NOTIFIED).values_list("data", flat=True))

    def test_never_queued_for_automated_mail_spam_or_a_merged_ticket(self):
        for values in (
            {"automated": True, "status": Status.CLOSED},
            {"status": Status.SPAM},
            {"status": Status.MERGED},
        ):
            ticket = new_ticket(**values)
            with self.subTest(values):
                self.update(ticket, assignee=self.kim)
                ticket.refresh_from_db()
                self.assertEqual(ticket.assignee, self.kim)  # assigned all the same
        self.assertEqual(self.claim_queued(), [])

    def test_never_queued_for_an_inactive_group(self):
        group = AssignmentGroup.objects.create(name="Events", is_active=False)
        group.members.add(self.kim)

        self.update(assignment_group=group)

        self.assertEqual(self.claim_queued(), [])

    def test_the_timeline_records_a_notice_once_it_went_out(self):
        self.update(assignee=self.kim)
        self.assertEqual(self.notified(), [])  # queued only

        (email,) = self.send(self.claim_queued())

        self.assertEqual(email.to, ("kim@example.com",))
        self.assertEqual(self.notified(), [{"reason": "assigned", "count": 1}])
        notice = self.ticket.events.get(kind=Kind.NOTIFIED)
        self.assertEqual(events.describe(notice), "Assignment notice emailed to the assignee")

    def test_nothing_goes_out_once_the_switch_is_off_or_shadow_mode_is_on(self):
        self.update(assignee=self.kim)
        queued = self.claim_queued()
        for values in ({"notify_assignment": False}, {"shadow_mode": True}):
            HelpdeskSettings.objects.update(**{"notify_assignment": True, "shadow_mode": False, **values})
            with self.subTest(values):
                self.assertEqual(self.send(queued), [])
        self.assertEqual(self.notified(), [])

    def test_nothing_goes_out_once_the_ticket_is_spam_merged_or_automated(self):
        self.update(assignee=self.kim)
        queued = self.claim_queued()
        for values in ({"status": Status.SPAM}, {"status": Status.MERGED}, {"automated": True}):
            Ticket.objects.filter(pk=self.ticket.pk).update(**{"status": Status.NEW, "automated": False, **values})
            with self.subTest(values):
                self.assertEqual(self.send(queued), [])
        self.assertEqual(self.notified(), [])

    def test_a_notice_goes_only_to_the_assignee_it_is_still_meant_for(self):
        sam = make_admin(email="sam@example.com", first_name="Sam", last_name="Diaz")
        self.update(assignee=self.kim)
        self.update(assignee=sam)  # reassigned before the first notice went out

        emails = self.send(self.claim_queued())

        self.assertEqual([email.to for email in emails], [("sam@example.com",)])
        self.assertEqual(self.notified(), [{"reason": "assigned", "count": 1}])

    def test_an_assignee_who_is_no_longer_an_admin_gets_nothing(self):
        self.update(assignee=self.kim)
        Member.objects.filter(pk=self.kim.pk).update(is_staff=False)

        self.assertEqual(self.send(self.claim_queued()), [])
        self.assertEqual(self.notified(), [])

    def test_a_group_notice_skips_members_who_left_the_group_or_are_no_longer_admins(self):
        third = make_admin(email="third@example.com")
        gone = make_admin(email="gone@example.com")
        group = AssignmentGroup.objects.create(name="Events")
        group.members.add(self.kim, third, gone)
        self.update(assignment_group=group)
        group.members.remove(gone)
        Member.objects.filter(pk=third.pk).update(is_active=False)

        (email,) = self.send(self.claim_queued())

        self.assertEqual(email.to, ("kim@example.com",))
        self.assertEqual(self.notified(), [{"reason": "group", "count": 1}])
        notice = self.ticket.events.get(kind=Kind.NOTIFIED)
        self.assertEqual(events.describe(notice), "Assignment notice emailed to the group's 1 member")

    def test_a_group_notice_goes_nowhere_once_the_group_is_off_or_someone_was_assigned(self):
        group = AssignmentGroup.objects.create(name="Events")
        group.members.add(self.kim)
        self.update(assignment_group=group)
        queued = self.claim_queued()

        AssignmentGroup.objects.filter(pk=group.pk).update(is_active=False)
        self.assertEqual(self.send(queued), [])
        AssignmentGroup.objects.filter(pk=group.pk).update(is_active=True)
        Ticket.objects.filter(pk=self.ticket.pk).update(assignee=self.kim)
        self.assertEqual(self.send(queued), [])
        self.assertEqual(self.notified(), [])

    def test_an_outsiders_link_never_reaches_a_notice(self):
        ticket = new_ticket(subject="Claim your prize at http://evil.example/x or www.evil.example")
        self.update(ticket, assignee=self.kim)

        (email,) = self.send(self.claim_queued())

        cleaned = "Claim your prize at [link removed] or [link removed]"
        self.assertEqual(email.subject, f"[{ticket.display_number}] Assigned to you: {cleaned}")
        self.assertIn(f"Subject: {cleaned}\n", email.text_body)
        self.assertNotIn("evil.example", email.text_body)
        self.assertEqual(email.headers, compose.NOTICE_HEADERS)
        self.assertEqual(
            compose.NOTICE_HEADERS, {"Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All"}
        )
        self.assertTrue(email.text_body.endswith(DO_NOT_REPLY))
