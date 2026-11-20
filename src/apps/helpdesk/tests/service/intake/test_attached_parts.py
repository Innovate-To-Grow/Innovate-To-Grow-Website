"""The messages a person attaches (forwards) are read to a summary within the limits: at most
``MAX_ATTACHED_MESSAGES`` of them, never their own attachments; a body part whose payload is not bytes reads as no
text."""

from email import message_from_bytes
from email.message import EmailMessage
from email.policy import SMTP

from django.test import SimpleTestCase

from ....services.ingest.reading import mime as parsing
from ....services.ingest.reading.message import MAX_ATTACHED_MESSAGES
from ....services.ingest.reading.parse import parse
from ... import corpus


def forwarding(count: int, *, inner_attachments=()) -> bytes:
    """A person forwarding ``count`` messages as attachments."""
    outer = EmailMessage(policy=SMTP)
    outer["From"] = "Pat Doe <pat@example.org>"
    outer["To"] = corpus.SITE
    outer["Subject"] = "Fwd: the earlier messages"
    outer["Message-ID"] = "<fwd-many@mail.example.org>"
    outer.set_content("See the messages below.")
    for index in range(count):
        inner = corpus.message(
            subject=f"Inner {index}", message_id=f"<inner-{index}@mail.example.org>", attachments=inner_attachments
        )
        outer.add_attachment(message_from_bytes(inner, policy=SMTP))
    return outer.as_bytes()


class AttachedMessageTests(SimpleTestCase):
    def test_at_most_the_cap_of_attached_messages_is_summarized(self):
        parsed = parse(forwarding(MAX_ATTACHED_MESSAGES + 2))

        self.assertEqual(
            [item["subject"] for item in parsed.attached_messages],
            [f"Inner {index}" for index in range(MAX_ATTACHED_MESSAGES)],
        )
        self.assertEqual(parsed.attachments, [])

    def test_an_attached_messages_own_attachments_are_not_kept(self):
        parsed = parse(forwarding(1, inner_attachments=[("report.pdf", b"%PDF-1.7 data", "application/pdf")]))

        (attached,) = parsed.attached_messages
        self.assertEqual(attached["subject"], "Inner 0")
        self.assertIn("showcase", attached["text"])
        self.assertEqual(parsed.attachments, [])

    def test_a_body_part_whose_payload_is_not_bytes_reads_as_no_text(self):
        class Part:
            def get_payload(self, decode=False):
                return None

        self.assertEqual(parsing._decode_text(Part()), "")
