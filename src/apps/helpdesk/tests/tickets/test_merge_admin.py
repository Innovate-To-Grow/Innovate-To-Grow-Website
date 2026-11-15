from django.contrib.admin import helpers
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.services.email.inbound import LABELS
from apps.helpdesk.tests.tickets.test_merge import (
    ACTION_SESSION_KEY,
    AUTOMATED_VIEW,
    BOUNCE_SENDER,
    CHANGELIST,
    EVERYTHING,
    Kind,
    Status,
    into_hidden,
    make_ticket,
    snapshot,
    spam_source,
)

from ...models import TicketEvent
from ...services import tickets
from ..helpers import helpdesk_staff


class MergeAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)
        self.bounce = make_ticket("Undeliverable", requester=BOUNCE_SENDER, automated=True, hours_ago=9)
        self.pat = make_ticket("Parking", hours_ago=8)
        self.kim = make_ticket("Parking too", requester="kim@example.org", hours_ago=7)
        self.spam = make_ticket(
            "You have won", requester="winner@lottery.example", automated=True, classification="spam"
        )

    def act(self, *selected, view=EVERYTHING, select_across=False, follow=False):
        data = {
            "action": "merge_tickets",
            "index": "0",
            "select_across": "1" if select_across else "0",
            helpers.ACTION_CHECKBOX_NAME: [str(ticket.pk) for ticket in selected],
        }
        return self.client.post(f"{reverse(CHANGELIST)}{view}", data, follow=follow)

    def confirm(self, word="MERGE"):
        token = self.client.session[ACTION_SESSION_KEY]["token"]
        url = reverse("admin:helpdesk_ticket_confirm_action")
        return self.client.post(url, {"confirmation_word": word, "token": token}, follow=True)

    def messages(self, response) -> list[str]:
        return [str(message) for message in get_messages(response.wsgi_request)]

    def listed(self, view) -> set[str]:
        return {ticket.subject for ticket in self.client.get(f"{reverse(CHANGELIST)}{view}").context["cl"].result_list}

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_a_merge_into_automated_mail_is_refused_before_the_typed_confirmation(self):
        before = snapshot()

        response = self.act(self.kim, self.bounce, self.pat)

        self.assertRedirects(response, f"{reverse(CHANGELIST)}{EVERYTHING}", fetch_redirect_response=False)
        self.assertNotIn(ACTION_SESSION_KEY, self.client.session)  # no confirmation was asked for
        self.assertEqual(self.messages(response), [into_hidden(self.bounce, f"automated mail ({LABELS['bounce']})")])
        self.assertEqual(snapshot(), before)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_select_all_takes_the_oldest_ticket_and_is_refused_on_it(self):
        before = snapshot()

        response = self.act(self.pat, select_across=True, follow=True)

        self.assertIn(into_hidden(self.bounce, f"automated mail ({LABELS['bounce']})"), self.messages(response))
        self.assertNotIn(ACTION_SESSION_KEY, self.client.session)
        self.assertEqual(snapshot(), before)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_spam_is_refused_as_part_of_a_merge(self):
        before = snapshot()

        response = self.act(self.pat, self.kim, self.spam, follow=True)

        self.assertEqual(self.messages(response), [spam_source(self.spam)])
        self.assertEqual(snapshot(), before)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_a_merge_that_turned_into_spam_after_the_confirmation_page_is_refused_when_it_runs(self):
        self.assertIn("confirm-action", self.act(self.pat, self.kim).url)
        tickets.mark_spam([self.pat], actor=helpdesk_staff(email="other.agent@example.com"))  # meanwhile
        before = snapshot()

        response = self.confirm()

        self.assertEqual(self.messages(response), [into_hidden(self.pat, "spam")])
        self.assertEqual(snapshot(), before)
        self.assertFalse(TicketEvent.objects.filter(kind=Kind.MERGED).exists())

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_peoples_tickets_still_merge_after_the_typed_word(self):
        response = self.act(self.kim, self.pat)
        self.assertIn("confirm-action", response.url)

        page = self.client.get(response.url)
        self.assertContains(page, "Merge into the oldest selected ticket (not automated mail or spam)")
        response = self.confirm()

        self.kim.refresh_from_db()
        self.assertEqual((self.kim.status, self.kim.merged_into), (Status.MERGED, self.pat))
        self.assertEqual(self.messages(response), [f"Merged into {self.pat.display_number}."])

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_automated_mail_merged_into_an_older_persons_ticket_stays_out_of_the_queue(self):
        reply = make_ticket(
            "Automatic reply: Parking", requester="pat@example.org", automated=True, classification="auto_reply"
        )

        response = self.act(reply, self.pat, follow=True)

        reply.refresh_from_db()
        self.assertEqual(self.messages(response), [f"Merged into {self.pat.display_number}."])
        self.assertEqual((reply.status, reply.automated, reply.merged_into), (Status.MERGED, True, self.pat))
        self.assertNotIn(reply.subject, self.listed("?status=any"))  # people's tickets, every status
        self.assertIn(reply.subject, self.listed(AUTOMATED_VIEW))
        self.assertEqual(self.listed(""), {"Parking", "Parking too"})  # the default queue is unchanged

    def test_the_automated_and_spam_view_offers_no_merge(self):
        def choices(view):
            response = self.client.get(f"{reverse(CHANGELIST)}{view}")
            return [name for name, _label in response.context["action_form"].fields["action"].choices]

        self.assertIn("merge_tickets", choices(EVERYTHING))
        self.assertIn("merge_tickets", choices(""))
        self.assertNotIn("merge_tickets", choices(AUTOMATED_VIEW))
        self.assertIn("move_to_queue", choices(AUTOMATED_VIEW))

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_a_merge_posted_to_the_automated_and_spam_view_does_nothing(self):
        before = snapshot()

        response = self.act(self.spam, self.bounce, view=AUTOMATED_VIEW, follow=True)

        self.assertEqual(self.messages(response), ["No action selected."])
        self.assertEqual(snapshot(), before)
