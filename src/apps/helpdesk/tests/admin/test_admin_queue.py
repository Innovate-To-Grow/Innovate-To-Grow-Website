"""Helpdesk → Queue: who may open it (every Admin), the default view (people's open tickets; automated mail
hidden), the filters and search, the bulk actions (merge and spam behind a typed confirmation), and the sidebar."""

from django.contrib.admin import helpers
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.event.tests.helpers import make_member
from config.settings.base.integrations.admin import navigation

from ...models import Ticket, TicketEvent
from ...services.tickets import numbering
from ..helpers import helpdesk_staff, make_admin

Status = Ticket.Status
CHANGELIST = "admin:helpdesk_ticket_changelist"
ACTION_SESSION_KEY = "_admin_pending_action_helpdesk_ticket"
CHANGE_SESSION_KEY = "_admin_pending_change_helpdesk_ticket"


def ticket(subject, **values) -> Ticket:
    values.setdefault("requester_email", "pat@example.org")
    return numbering.create_ticket(subject=subject, **values)


class QueueTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)
        self.open = ticket("Open question", status=Status.OPEN, unread=True)
        self.new = ticket("New question")
        self.closed = ticket("Closed question", status=Status.CLOSED, closed_at=timezone.now())
        self.automated = ticket(
            "Automatic reply: hi",
            status=Status.CLOSED,
            automated=True,
            classification="auto_reply",
            closed_at=timezone.now(),
        )
        self.spam = ticket("Win a prize", status=Status.SPAM, automated=True, classification="spam")

    def listed(self, **params) -> set[str]:
        response = self.client.get(reverse(CHANGELIST), params)
        self.assertEqual(response.status_code, 200)
        return {item.subject for item in response.context["cl"].result_list}


class AccessTests(QueueTestCase):
    def test_members_who_are_not_admins_are_sent_to_the_login_page_everywhere(self):
        self.client.force_login(make_member(email="member@example.com"))
        urls = [
            reverse(CHANGELIST),
            reverse("admin:helpdesk_ticket_change", args=[self.open.pk]),
            reverse("admin:helpdesk_ingestrecord_changelist"),
            reverse("admin:helpdesk_ticketcategory_changelist"),
            reverse("admin:helpdesk_helpdesksettings_changelist"),
        ]
        for url in urls:
            with self.subTest(url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])
        note = self.client.post(reverse("admin:helpdesk_ticket_note", args=[self.open.pk]), {"body": "x"})
        self.assertIn("/login/", note["Location"])
        self.assertFalse(self.open.messages.exists())

    def test_every_admin_opens_the_queue(self):
        self.assertEqual(self.client.get(reverse(CHANGELIST)).status_code, 200)
        self.client.force_login(make_admin(email="other-admin@example.com"))
        self.assertEqual(self.client.get(reverse(CHANGELIST)).status_code, 200)

    def test_tickets_are_never_added_by_hand_and_any_admin_may_delete_one(self):
        self.assertEqual(self.client.get(reverse("admin:helpdesk_ticket_add")).status_code, 403)
        delete = reverse("admin:helpdesk_ticket_delete", args=[self.open.pk])
        self.assertEqual(self.client.get(delete).status_code, 200)
        response = self.client.get(reverse(CHANGELIST))
        self.assertIn("delete_selected", dict(response.context["action_form"].fields["action"].choices))

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_deleting_a_ticket_still_needs_the_typed_confirmation(self):
        # Only the ticket page's save skips it: a delete takes the messages, files and audit trail with it.

        response = self.client.post(reverse("admin:helpdesk_ticket_delete", args=[self.open.pk]), {"post": "yes"})

        self.assertIn("confirm-change", response.url)
        self.assertTrue(Ticket.objects.filter(pk=self.open.pk).exists())
        token = self.client.session[CHANGE_SESSION_KEY]["token"]
        self.client.post(
            reverse("admin:helpdesk_ticket_confirm_change"), {"confirmation_word": "ticket", "token": token}
        )
        self.assertFalse(Ticket.objects.filter(pk=self.open.pk).exists())


class ListTests(QueueTestCase):
    def test_the_default_view_is_peoples_open_tickets(self):
        response = self.client.get(reverse(CHANGELIST))

        self.assertEqual(
            {item.subject for item in response.context["cl"].result_list}, {"Open question", "New question"}
        )
        self.assertContains(response, "Shadow mode.")
        self.assertContains(response, "i2g-helpdesk-unread")

    def test_automated_mail_and_spam_are_shown_on_request(self):
        self.assertEqual(self.listed(mail="automated"), {"Automatic reply: hi", "Win a prize"})
        self.assertEqual(self.listed(mail="automated", status="open"), set())
        self.assertEqual(len(self.listed(mail="all")), 5)
        self.assertEqual(self.listed(mail="all", status="open"), {"Open question", "New question"})

    def test_status_filters(self):
        self.assertEqual(self.listed(status="closed"), {"Closed question"})
        self.assertEqual(self.listed(status="new"), {"New question"})
        self.assertEqual(self.listed(status="any"), {"Open question", "New question", "Closed question"})

    def test_assignee_and_unread_filters(self):
        Ticket.objects.filter(pk=self.open.pk).update(assignee=self.agent)

        self.assertEqual(self.listed(assignee="me"), {"Open question"})
        self.assertEqual(self.listed(assignee="none"), {"New question"})
        self.assertEqual(self.listed(unread="yes"), {"Open question"})

    def test_a_number_also_searches_subjects(self):
        dated = ticket("Showcase 2026 parking", status=Status.OPEN)

        self.assertEqual(self.listed(q="2026"), {dated.subject})
        self.assertEqual(self.listed(q=str(self.new.number)), {"New question"})

    def test_search_by_number_subject_or_requester(self):
        self.assertEqual(self.listed(q=self.new.display_number), {"New question"})
        self.assertEqual(self.listed(q=str(self.open.number)), {"Open question"})
        self.assertEqual(self.listed(q="New quest"), {"New question"})
        self.assertEqual(self.listed(q="pat@example.org"), {"Open question", "New question"})

    def test_the_selected_filter_choice_is_marked(self):
        response = self.client.get(reverse(CHANGELIST))
        filters = {
            spec.title: list(spec.choices(response.context["cl"])) for spec in response.context["cl"].filter_specs
        }

        mail = {choice["display"]: choice["selected"] for choice in filters["mail"]}
        status = {choice["display"]: choice["selected"] for choice in filters["status"]}
        self.assertTrue(mail["People (default)"])
        self.assertTrue(status["Open (new, open, pending)"])


class _ActionCase(QueueTestCase):
    def act(self, action, *tickets, follow=False):
        data = {
            "action": action,
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(item.pk) for item in tickets],
        }
        # The changelist form posts back to the view it shows (its filters in the query string): here, everything.
        return self.client.post(f"{reverse(CHANGELIST)}?mail=all&status=any", data, follow=follow)


class ActionTests(_ActionCase):
    def test_everyday_actions_run_at_once(self):
        self.act("assign_to_me", self.open, self.new)
        self.act("mark_read", self.open)
        self.act("close_tickets", self.new)
        self.act("reopen_tickets", self.new, self.automated)
        self.act("unassign", self.open)

        self.open.refresh_from_db()
        self.new.refresh_from_db()
        self.automated.refresh_from_db()
        self.assertEqual((self.open.assignee, self.open.unread), (None, False))
        self.assertEqual((self.new.status, self.new.assignee), (Status.OPEN, self.agent))
        self.assertEqual(self.automated.status, Status.CLOSED)  # automated mail is moved, never reopened
        self.assertEqual(
            list(self.new.events.values_list("kind", flat=True)),
            [TicketEvent.Kind.ASSIGNED, TicketEvent.Kind.STATUS, TicketEvent.Kind.STATUS],
        )


class SidebarTests(TestCase):
    def active_items(self, path):
        request = RequestFactory().get(path)
        section = next(item for item in navigation.SIDEBAR["navigation"] if item["title"] == "Helpdesk")
        return [item["title"] for item in section["items"] if callable(item.get("active")) and item["active"](request)]

    def test_each_view_of_the_ticket_list_lights_its_own_entry(self):
        self.assertEqual(self.active_items("/admin/helpdesk/ticket/"), ["Queue"])
        self.assertEqual(self.active_items("/admin/helpdesk/ticket/?assignee=me"), ["My Tickets"])
        self.assertEqual(self.active_items("/admin/helpdesk/ticket/?assignee=none"), ["Unassigned"])
        self.assertEqual(self.active_items("/admin/helpdesk/ticket/?mail=automated&status=any"), ["Automated & Spam"])
        self.assertEqual(self.active_items("/admin/helpdesk/ingestrecord/"), [])

    def test_the_section_is_shown_to_admins_only(self):
        section = next(item for item in navigation.SIDEBAR["navigation"] if item["title"] == "Helpdesk")
        request = RequestFactory().get("/admin/")
        request.user = make_member(email="member@example.com")
        self.assertFalse(section["permission"](request))
        request.user = helpdesk_staff()
        self.assertTrue(section["permission"](request))
