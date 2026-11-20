"""Shadow mode: while it is on, the helpdesk reads the mailbox and writes tickets, and sends nothing.

Three layers of proof: outside ``services/outbound`` (the one module that sends, and checks shadow mode first) the
helpdesk's code imports no sending API at all, and nowhere does it use Django's mail or the Graph transport; a whole
ingest of every kind of mail runs with every sending path (the email facade, Django's mail, the Graph POST transport)
wired to fail the test; and the only thing it asks of the mailbox is a GET of a message's MIME (the Graph allow-list
refuses anything else anyway).
"""

import ast
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from ...models import HelpdeskSettings, Ticket
from ...services.tickets import shadow
from .. import corpus
from ..helpers import FakeReader, ingest, queue

HELPDESK_ROOT = Path(__file__).resolve().parents[2]
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
    "apps.core.services.email.sending.delivery",
    "django.core.mail",
)
# Never anywhere, the sending module included: it sends through the email facade only.
ALWAYS_FORBIDDEN_MODULES = ("apps.core.services.email.graph.transport", "django.core.mail")
OUTBOUND = ("services", "outbound")


class ShadowSwitchTests(TestCase):
    def test_shadow_mode_is_on_by_default_and_nothing_may_send(self):
        self.assertTrue(HelpdeskSettings().shadow_mode)
        self.assertTrue(shadow.shadow_mode_on())
        self.assertFalse(shadow.sending_allowed())

    def test_switched_off_sending_is_allowed(self):
        settings = HelpdeskSettings(shadow_mode=False)

        self.assertTrue(shadow.SENDING_IMPLEMENTED)
        self.assertFalse(shadow.shadow_mode_on(settings))
        self.assertTrue(shadow.sending_allowed(settings))

    def test_the_code_switch_still_overrides_the_setting(self):
        with patch.object(shadow, "SENDING_IMPLEMENTED", False):
            self.assertFalse(shadow.sending_allowed(HelpdeskSettings(shadow_mode=False)))


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield node.module or "", {alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, set()


def _calling(path: Path, callee: str):
    """The names of the functions in ``path`` that call ``callee`` (by its name or as an attribute)."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef) and any(
            isinstance(call, ast.Call) and callee in (getattr(call.func, "id", ""), getattr(call.func, "attr", ""))
            for call in ast.walk(node)
        ):
            yield node.name


def _function(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    nodes = (node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef))
    return ast.get_source_segment(source, next(node for node in nodes if node.name == name))


class NoSendingCodeTests(TestCase):
    def test_only_the_outbound_module_imports_a_sending_api(self):
        offenders = []
        for path in sorted(HELPDESK_ROOT.rglob("*.py")):
            relative = path.relative_to(HELPDESK_ROOT)
            if "tests" in relative.parts or "migrations" in relative.parts:
                continue
            sender = relative.parts[:2] == OUTBOUND
            for module, names in _imports(path):
                if module.startswith(ALWAYS_FORBIDDEN_MODULES) or "post" in names:
                    offenders.append(f"{relative}: {module} {sorted(names)}")
                elif not sender and (module.startswith(FORBIDDEN_MODULES) or names & FORBIDDEN_NAMES):
                    offenders.append(f"{relative}: {module} {sorted(names)}")

        self.assertEqual(offenders, [])

    def test_every_send_checks_shadow_mode_first(self):
        outbound = HELPDESK_ROOT.joinpath(*OUTBOUND)
        senders = {
            (path.name, name) for path in sorted(outbound.glob("*.py")) for name in _calling(path, "deliver_email")
        }
        # The two sending handlers are the only code that hands mail to the email facade.
        self.assertEqual(senders, {("jobs.py", "send_reply_job"), ("notifications.py", "notify_staff_job")})
        reply = _function(outbound / "jobs.py", "send_reply_job")
        self.assertLess(reply.index("shadow.sending_allowed("), reply.index("deliver_email("))
        notice = _function(outbound / "notifications.py", "notify_staff_job")
        self.assertLess(notice.index("_due("), notice.index("deliver_email("))
        # ``_due`` is where the notice job checks shadow mode (with the notify switch and the ticket's state).
        self.assertIn("shadow.sending_allowed(settings)", _function(outbound / "notifications.py", "_due"))


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
            patch("apps.core.services.email.sending.delivery.EmailDeliveryService.send", side_effect=refuse) as facade,
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
