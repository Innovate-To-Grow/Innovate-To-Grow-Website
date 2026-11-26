"""Moving misclassified mail to the queue makes it a person's ticket in full (after the third live check of the
admin): classified as a person's, the requester's messages theirs again (shown as the requester's, quoted under a
reply) and, when the scam checks scored them, flagged suspicious rather than spam; another sender's automated mail on
the ticket stays as it was. A member's message that asked for replies at her other address (the same name) stays
hers: the member link is kept, and the timeline names the address as hers, not a web form's. A mailing list without
List-Post is known by its List-Id (``name@domain`` for ``name.domain``), else as the address its mail is sent To and
comes from: its poster's message moved to the queue is the poster's, never the list's, and her own other address in
Reply-To is no list."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, Member

from ...models import Ticket, TicketMessage
from ...services import outbound, tickets
from ...services.outbound.replies import ReplyRefused, last_inbound, parse_cc
from ...services.tickets import events
from .. import corpus
from ..helpers import helpdesk_staff, receive
from ..helpers.service import sending_settings
from ..service.intake.scam_mail import DMARC_PASS, locked_out

Status = Ticket.Status
Kind = TicketMessage.Kind
ANNOUNCE = "faculty-announce@lists.example.edu"
UNPOSTED = {"List-Id": "Faculty Announce <faculty-announce.lists.example.edu>", "Precedence": "list"}
GROUP = "faculty-ann@googlegroups.example"
LIST_ON_DOMAIN = "faculty-list@lists.example.edu"
IRA = "Ira Moss <ira.moss@example.edu>"


class MovedToQueueTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)

    def moved(self, ticket):
        self.assertEqual(tickets.move_to_queue([ticket], actor=self.agent), 1)
        ticket.refresh_from_db()
        return ticket

    def test_mail_the_scam_checks_made_spam_becomes_the_requesters_suspicious_message(self):
        spam = receive(locked_out())
        self.assertEqual((spam.status, spam.classification), (Status.SPAM, "spam"))

        ticket = self.moved(spam)

        message = ticket.messages.get()
        self.assertEqual((ticket.classification, ticket.flags, ticket.automated), ("human", ["suspicious"], False))
        self.assertEqual((message.kind, message.classification, message.scam_level), (Kind.CUSTOMER, "human", "medium"))
        self.assertEqual(last_inbound(ticket), message)  # quoted under the first reply
        page = self.client.get(reverse("admin:helpdesk_ticket_change", args=[ticket.pk]))
        self.assertContains(page, "Suspicious: the scam checks found warning signs.")
        self.assertNotContains(page, "Marked as spam by the scam checks.")

    def test_mail_exchange_rated_spam_is_not_flagged(self):
        ticket = self.moved(receive(corpus.spam()))

        message = ticket.messages.get()
        self.assertEqual((message.kind, message.classification, message.scam_level), (Kind.CUSTOMER, "human", ""))
        self.assertEqual((ticket.classification, ticket.flags), ("human", []))

    def test_another_senders_automated_mail_stays_automated(self):
        spam = receive(locked_out())
        reply = corpus.out_of_office(sender="Kim Lee <kim@example.org>", in_reply_to="<locked-1@mail.example.org>")
        self.assertEqual(receive(reply).pk, spam.pk)

        ticket = self.moved(spam)

        kinds = dict(ticket.messages.values_list("from_address", "kind"))
        self.assertEqual(kinds, {"pat@example.org": Kind.CUSTOMER, "kim@example.org": Kind.AUTOMATED})

    def test_a_members_message_naming_her_other_address_stays_hers_once_moved(self):
        dana = Member.objects.create_user(password="x", first_name="Dana", last_name="Member")
        ContactEmail.objects.create(member=dana, email_address="dana@example.com", email_type="primary", verified=True)
        headers = {"Authentication-Results": DMARC_PASS, "Reply-To": "Dana Member <dana@home.example>"}
        spam = receive(
            corpus.message(
                sender="Dana Member <dana@example.com>", headers={**headers, "X-MS-Exchange-Organization-SCL": "5"}
            )
        )

        Ticket.objects.filter(pk=spam.pk).update(participants=[])  # a ticket from before its people were listed
        ticket = self.moved(spam)

        self.assertEqual((ticket.requester_email, ticket.requester_member), ("dana@home.example", dana))
        self.assertIn("dana@home.example", ticket.participants)
        moved = ticket.events.get(kind="reclassified")
        self.assertEqual(
            events.describe(moved),
            "Moved to the queue; its requester is now dana@home.example, the sender's other address it asked replies "
            "to go to",
        )


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class UnpostedListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.settings = sending_settings()

    def moved(self, sender, number, *, to=ANNOUNCE, listing=UNPOSTED, raw=False, **headers):
        if not raw:
            sender = corpus.message(sender=sender, to=to, message_id=f"<a-{number}@x>", headers={**listing, **headers})
        raw = sender
        ticket = receive(raw)
        self.assertEqual(tickets.move_to_queue([ticket], actor=self.agent), 1)
        ticket.refresh_from_db()
        return ticket

    def test_historical_rewritten_from_remains_blocked_after_moving_to_queue(self):
        from importlib import import_module

        from django.apps import apps
        from django.db import connection

        raw = corpus.message(sender=f"Ira via Faculty <{ANNOUNCE}>", to=ANNOUNCE, headers=UNPOSTED)
        ticket = receive(raw)
        ticket.messages.update(list_address="", on_behalf_of="", on_behalf_name="")
        migration = import_module("apps.helpdesk.migrations.0006_guard_legacy_list_senders")
        migration.guard_legacy_list_senders(apps, connection.schema_editor())
        self.assertEqual(tickets.move_to_queue([ticket], actor=self.agent), 1)
        ticket.refresh_from_db()
        with self.assertRaisesMessage(ReplyRefused, "is a mailing list"):
            outbound.queue_reply(ticket, actor=self.agent, body="Following up")

    def test_list_mail_rewriting_its_poster_belongs_to_the_poster(self):
        munged = f"Ira Moss via Faculty Announce <{ANNOUNCE}>"
        found = {
            "Reply-To the poster": (ANNOUNCE, self.moved(munged, 1, **{"Reply-To": IRA})),
            "the poster in Cc": (ANNOUNCE, self.moved(munged, 2, **{"Reply-To": ANNOUNCE, "Cc": IRA})),
            "Google Groups": (
                GROUP,
                self.moved(
                    f"'Ira Moss' via Faculty <{GROUP}>",
                    3,
                    to=GROUP,
                    listing={"List-Id": f"<{GROUP.replace('@', '.')}>"},
                    **{"Reply-To": GROUP, "X-Original-From": IRA},
                ),
            ),  # fmt: skip
            "a List-Id naming no address": (
                ANNOUNCE,
                self.moved(munged, 4, listing={"List-Id": "<news.example.edu>"}, **{"Reply-To": IRA}),
            ),
        }
        for case, (listed, ticket) in found.items():
            with self.subTest(case):
                self.assertEqual((ticket.requester_name, ticket.requester_email), ("Ira Moss", "ira.moss@example.edu"))
                self.assertEqual(
                    (ticket.messages.get().list_address, outbound.can_reply(ticket, self.settings)), (listed, "")
                )
                self.assertNotIn(listed, ticket.participants)

    def test_a_reply_to_on_the_list_ids_domain_is_the_list_when_the_list_id_names_no_address(self):
        listing, listed = {"List-Id": "Faculty <faculty.lists.example.edu>", "Precedence": "list"}, LIST_ON_DOMAIN
        ticket = self.moved(IRA, 6, to=corpus.SITE, listing=listing, **{"Reply-To": listed})  # personal delivery

        self.assertEqual((ticket.requester_email, ticket.messages.get().list_address), ("ira.moss@example.edu", listed))
        self.assertNotIn(listed, ticket.participants)
        with self.assertRaisesMessage(ReplyRefused, f"{listed} is a mailing list"):
            parse_cc(listed, ticket)

    def test_a_colleague_on_the_list_ids_domain_is_no_list(self):
        cases = (("faculty-announce", "eng.office@example.edu"), ("faculty", "faculty.affairs@example.edu"))
        for number, (label, office) in enumerate(cases, 7):  # also one named like the list, on her own domain
            with self.subTest(office):
                listing = {"List-Id": f"Faculty <{label}.example.edu>", "Precedence": "list"}
                ticket = self.moved(IRA, number, to=corpus.SITE, listing=listing, **{"Reply-To": f"Office <{office}>"})

                self.assertEqual(ticket.messages.get().list_address, "")
                self.assertEqual(parse_cc(office, ticket), [office])

    def test_a_relayed_persons_address_her_member_never_verified_gives_no_member_link(self):
        eve = Member.objects.create_user(password="x", first_name="Eve", last_name="Member")
        ContactEmail.objects.create(member=eve, email_address="victor@example.net", email_type="other")
        raw = corpus.message(sender="Form <forms@relay.example>", message_id="<rv@x>",
                             headers={"Reply-To": "Victor <victor@example.net>", "Precedence": "bulk"})  # fmt: skip
        ticket = self.moved(raw, 9, raw=True)

        self.assertEqual((ticket.requester_email, ticket.requester_member), ("victor@example.net", None))

    def test_a_posters_own_other_address_in_reply_to_is_no_list(self):
        ticket = self.moved(IRA, 5, **{"Reply-To": "Ira Moss <ira.home@home.example>"})

        self.assertEqual(
            (ticket.requester_email, ticket.messages.get().list_address), ("ira.moss@example.edu", ANNOUNCE)
        )
        self.assertEqual(parse_cc("ira.home@home.example", ticket), ["ira.home@home.example"])
        self.assertNotIn(ANNOUNCE, outbound.cc_suggestions(ticket))
