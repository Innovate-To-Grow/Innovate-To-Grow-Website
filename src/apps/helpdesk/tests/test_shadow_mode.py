"""Shadow mode: the helpdesk reads the mailbox and writes tickets, and sends nothing, ever.

Three layers of proof: the helpdesk's code imports no sending API at all; a whole ingest of every kind of mail runs
with every sending path (the email facade, Django's mail, the Graph POST transport) wired to fail the test; and the
only thing it asks of the mailbox is a GET of a message's MIME (the Graph allow-list refuses anything else anyway).
"""

import ast
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from ..models import HelpdeskSettings, Ticket
from ..services import shadow
from . import corpus
from .helpers import FakeReader, ingest, queue

HELPDESK_ROOT = Path(__file__).resolve().parents[1]
# Any of these in the helpdesk's own code would be a way to send mail or change the mailbox.
FORBIDDEN_NAMES = {
    "deliver_email",
    "send_mail",
    "send_mass_mail",
    "mail_admins",
    "EmailMessage",
    "EmailMultiAlternatives",
    "GraphProvider",
    "SESProvider",
    "SMTPProvider",
    "send_notification_email",
    "post",
}
FORBIDDEN_MODULES = (
    "apps.core.services.email.graph.transport",
    "apps.core.services.email.delivery",
    "django.core.mail",
)


class ShadowSwitchTests(TestCase):
    def test_shadow_mode_is_on_by_default_and_nothing_may_send(self):
        self.assertTrue(HelpdeskSettings().shadow_mode)
        self.assertTrue(shadow.shadow_mode_on())
        self.assertFalse(shadow.sending_allowed())

    def test_even_switched_off_nothing_may_send_in_this_release(self):
        settings = HelpdeskSettings(shadow_mode=False)

        self.assertFalse(shadow.SENDING_IMPLEMENTED)
        self.assertTrue(shadow.shadow_mode_on(settings))
        self.assertFalse(shadow.sending_allowed(settings))


class NoSendingCodeTests(TestCase):
    def test_the_helpdesk_imports_no_sending_api(self):
        offenders = []
        for path in sorted(HELPDESK_ROOT.rglob("*.py")):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    names = {alias.name for alias in node.names}
                    if module.startswith(FORBIDDEN_MODULES) or names & FORBIDDEN_NAMES:
                        offenders.append(f"{path.relative_to(HELPDESK_ROOT)}: from {module} import {sorted(names)}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(FORBIDDEN_MODULES):
                            offenders.append(f"{path.relative_to(HELPDESK_ROOT)}: import {alias.name}")

        self.assertEqual(offenders, [])


class NothingIsSentTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_ingesting_every_kind_of_mail_sends_nothing_and_only_reads(self):
        reader = FakeReader()
        samples = (
            corpus.message(),
            corpus.message(message_id="<r@x>", in_reply_to="<m1@mail.example.org>"),
            corpus.out_of_office(),
            corpus.gmail_vacation(),
            corpus.left_organisation(),
            corpus.german_auto_reply(),
            corpus.bounce_report(),
            corpus.read_receipt(),
            corpus.calendar_reply(),
            corpus.list_mail(),
            corpus.esp_newsletter(),
            corpus.spam(),
            corpus.own_message(),
            corpus.forwarded(),
        )
        for raw in samples:
            queue(raw, reader=reader)
        refuse = AssertionError("shadow mode: nothing may be sent")

        with (
            patch("apps.core.services.email.delivery.EmailDeliveryService.send", side_effect=refuse) as facade,
            patch("django.core.mail.send_mail", side_effect=refuse) as django_mail,
            patch("django.core.mail.EmailMessage.send", side_effect=refuse) as django_message,
            patch("apps.core.services.email.graph.transport.post", side_effect=refuse) as graph_post,
        ):
            outcome = ingest(reader)

        self.assertEqual((outcome.processed, outcome.failed), (len(samples), 0))
        self.assertEqual(Ticket.objects.count(), len(samples) - 1)  # the reply joined its ticket
        for sender in (facade, django_mail, django_message, graph_post):
            sender.assert_not_called()
        self.assertEqual(len(reader.fetched), len(samples))
