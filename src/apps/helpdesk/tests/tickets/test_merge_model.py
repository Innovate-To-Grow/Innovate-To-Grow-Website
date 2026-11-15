import uuid

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.helpdesk.tests.tickets.test_merge import Status, make_ticket

from ...models import Ticket
from ...services import tickets
from ..helpers import helpdesk_staff


class MergeModelTests(TestCase):
    """``Ticket.clean`` refuses the same targets for any form or ``full_clean()`` path."""

    def setUp(self):
        cache.clear()
        self.ticket = make_ticket("Question")

    def refusal(self, target) -> list[str]:
        self.ticket.merged_into = target
        with self.assertRaises(ValidationError) as refused:
            self.ticket.full_clean()
        return refused.exception.messages

    def test_a_new_merge_target_that_is_automated_mail_or_spam_is_refused(self):
        bounce = make_ticket("Undeliverable", automated=True)
        classified = make_ticket("You have won", automated=True, classification="spam")
        marked = make_ticket("Cheap watches", status=Status.SPAM)

        self.assertEqual(
            self.refusal(bounce),
            [f"Nothing is merged into automated mail or spam, and {bounce.display_number} is automated mail."],
        )
        for spam in (classified, marked):
            with self.subTest(spam.subject):
                self.assertEqual(
                    self.refusal(spam),
                    [f"Nothing is merged into automated mail or spam, and {spam.display_number} is spam."],
                )

    def test_a_ticket_merges_only_into_another_ticket_that_is_not_merged(self):
        merged = make_ticket("Merged", status=Status.MERGED)
        message = ["A ticket can only be merged into another ticket that is not merged itself."]

        self.assertEqual(self.refusal(self.ticket), message)
        self.assertEqual(self.refusal(merged), message)
        self.ticket.merged_into_id = uuid.uuid4()
        with self.assertRaises(ValidationError) as missing:
            self.ticket.full_clean()
        self.assertEqual(list(missing.exception.message_dict), ["merged_into"])  # the field's own check

    def test_a_persons_ticket_is_a_valid_target_and_an_earlier_merge_is_not_judged_again(self):
        later = make_ticket("Same question")
        later.merged_into = self.ticket
        later.full_clean()  # a person's ticket may be the target

        tickets.merge([later, self.ticket], actor=helpdesk_staff())
        Ticket.objects.filter(pk=self.ticket.pk).update(status=Status.SPAM)  # the target is marked spam afterwards
        later.refresh_from_db()

        self.assertEqual(later.merged_into, self.ticket)
        later.full_clean()  # the merge made earlier is not judged again
        make_ticket("Unmerged").full_clean()
