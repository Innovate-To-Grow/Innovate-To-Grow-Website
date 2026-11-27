"""What a helpdesk email says: placeholders (with an outsider's links removed), the subject with the ticket token,
the footer and the quoted HTML."""

from django.test import TestCase
from django.utils import timezone

from ....models import TicketMessage
from ....services.outbound import compose
from ...helpers import helpdesk_staff
from ...helpers.service import new_ticket


class FillTests(TestCase):
    def test_every_placeholder(self):
        ticket = new_ticket(subject="Judging", requester_name="Pat Doe")

        text = compose.fill(
            "{ticket} {requester_name} {subject} {agent_name} {unknown}", ticket, agent=helpdesk_staff()
        )

        self.assertEqual(text, f"{ticket.display_number} Pat Doe Judging Avery Agent {{unknown}}")

    def test_fallbacks_for_empty_values(self):
        ticket = new_ticket(subject="", requester_name="")

        self.assertEqual(
            compose.fill("{requester_name}|{subject}|{agent_name}", ticket),
            "there|(no subject)|the Innovate to Grow team",
        )

    def test_links_an_outsider_chose_are_removed_but_the_templates_own_stay(self):
        for name in ("http://evil.example/login", "Visit www.evil.example now", "Pat evil.example/login"):
            ticket = new_ticket(requester_name=name, subject=f"Hi {name}")
            with self.subTest(name):
                text = compose.fill("{requester_name} | {subject} | https://i2g.ucmerced.edu/help", ticket)
                self.assertNotIn("evil.example", text)
                self.assertIn("[link removed]", text)
                self.assertTrue(text.endswith("https://i2g.ucmerced.edu/help"))

    def test_a_name_that_is_only_a_link_is_replaced_entirely(self):
        ticket = new_ticket(requester_name="https://evil.example")

        self.assertEqual(compose.fill("{requester_name}", ticket), "[link removed]")


class SubjectTests(TestCase):
    def test_reply_prefixes_and_old_tokens_are_dropped_and_the_token_added(self):
        ticket = new_ticket(subject="RE: Fwd: Question [I2G-#77]")

        self.assertEqual(compose.reply_subject(ticket), f"Re: Question [{ticket.display_number}]")

    def test_an_empty_subject_and_a_long_one(self):
        empty = new_ticket(subject="")
        long = new_ticket(subject="x" * 255)

        self.assertEqual(compose.reply_subject(empty), f"Re: Your message [{empty.display_number}]")
        subject = compose.reply_subject(long)
        self.assertLessEqual(len(subject), 255)
        self.assertTrue(subject.endswith(f" [{long.display_number}]"))

    def test_a_link_in_the_subject_is_removed(self):
        ticket = new_ticket(subject="Claim at http://evil.example/x")

        self.assertEqual(compose.reply_subject(ticket), f"Re: Claim at [link removed] [{ticket.display_number}]")

    def test_the_filled_in_subject_and_the_reply_subject_name_only_the_tickets_own_number(self):
        # Both kept "Re:" and the number of the ticket the sender named: "about Re: … [I2G-#1006] … ticket I2G-#1019".
        ticket = new_ticket(subject="Re: Judges briefing time for the showcase [I2G-#1006]")
        number, subject = ticket.display_number, "Judges briefing time for the showcase"

        for strict in (False, True):  # an inserted template, and the acknowledgement
            with self.subTest(strict=strict):
                self.assertEqual(
                    compose.fill("About {subject} ({ticket})", ticket, strict=strict), f"About {subject} ({number})"
                )
        self.assertEqual(compose.clean_subject(ticket, strict=True), subject)
        self.assertEqual(compose.reply_subject(ticket), f"Re: {subject} [{number}]")

    def test_what_is_left_of_the_subject_without_its_numbers_and_prefixes(self):
        between = new_ticket(subject="Fwd: Badges [I2G-#1006] for Friday")
        nothing = new_ticket(subject="RE: Fwd: [I2G-#1006]")

        self.assertEqual(compose.fill("{subject}", between), "Badges for Friday")
        self.assertEqual(compose.fill("{subject}", nothing), "(no subject)")
        for subject in (
            "Fwd: [I2G-#5] Re: Badges (I2G-#4)",
            "[EXTERNAL] AW: WG: Badges {I2G-#7}",
            "回复：Badges [ I2G-#4 ]",
        ):
            with self.subTest(subject):
                self.assertEqual(compose.fill("{subject}", new_ticket(subject=subject)), "Badges")
        self.assertEqual(compose.fill("{subject}", new_ticket(subject="[Faculty] Re: Badges")), "[Faculty] Badges")
        for subject in ("VB: Badges", "[EXTERNAL EMAIL] Re: Badges", "Re: Badges [I2G-#4, I2G-#5]", "ΠΡΘ: Badges",
                        "Re: Badges [I2G-#4 I2G-#5]", "Badges (I2G-#4 and I2G-#5)"):  # fmt: skip
            with self.subTest(subject):
                self.assertEqual(compose.fill("{subject}", new_ticket(subject=subject)), "Badges")
        for subject in ("Is <> allowed?", "Fill the [ ] box", "R: help with ggplot"):  # the sender's own words
            with self.subTest(subject):
                self.assertEqual(compose.fill("{subject}", new_ticket(subject=subject)), subject)
        self.assertEqual(compose.clean_subject(nothing, strict=True), "")


class BodyTests(TestCase):
    def test_the_text_ends_with_the_ticket_footer(self):
        ticket = new_ticket()

        text = compose.reply_text("  Hello.  ", ticket)

        self.assertEqual(
            text,
            f"Hello.\n\n--\nTicket {ticket.display_number}. Reply to this email to add to it, and keep "
            f"{ticket.display_number} in the subject.",
        )

    def test_the_html_quotes_the_message_it_answers_escaped(self):
        ticket = new_ticket()
        quoted = TicketMessage(
            ticket=ticket,
            kind=TicketMessage.Kind.CUSTOMER,
            from_name="Pat Doe",
            from_address="pat@example.org",
            occurred_at=timezone.now(),
            body_text="When <b>does</b> it start?",
        )

        html = compose.reply_html("See you there.", ticket, quoted)

        self.assertIn("See you there.", html)
        self.assertIn("Pat Doe", html)
        self.assertIn("When &lt;b&gt;does&lt;/b&gt; it start?", html)

    def test_a_purged_body_is_not_quoted(self):
        ticket = new_ticket()
        quoted = TicketMessage(
            ticket=ticket,
            kind=TicketMessage.Kind.CUSTOMER,
            occurred_at=timezone.now(),
            body_text="secret words",
            body_purged_at=timezone.now(),
        )

        self.assertNotIn("secret words", compose.reply_html("Hi", ticket, quoted))
        self.assertIn("Hi", compose.reply_html("Hi", ticket))

    def test_person(self):
        self.assertEqual(compose.person(None), "")
        self.assertEqual(compose.person(helpdesk_staff()), "Avery Agent")
