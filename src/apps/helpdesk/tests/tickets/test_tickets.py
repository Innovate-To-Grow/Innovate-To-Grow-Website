"""Ticket numbers, staff actions on tickets (each in the audit trail), retention, and the event descriptions."""

from unittest.mock import patch

from django.db import IntegrityError, connection
from django.test import TestCase, TransactionTestCase

from ...models import Ticket, TicketEvent
from ...services.tickets import numbering

Status = Ticket.Status
Kind = TicketEvent.Kind


def new_ticket(**values) -> Ticket:
    values.setdefault("subject", "Question")
    values.setdefault("requester_email", "pat@example.org")
    return numbering.create_ticket(**values)


class NumberingTests(TestCase):
    def test_numbers_start_at_1001_and_never_repeat(self):
        numbers = [new_ticket().number for _ in range(5)]

        self.assertEqual(len(set(numbers)), 5)
        self.assertEqual(numbers, sorted(numbers))
        self.assertGreaterEqual(numbers[0], numbering.FIRST_NUMBER)
        if connection.vendor != "postgresql":
            self.assertEqual(numbers[0], 1001)

    def test_postgresql_numbers_come_from_the_sequence_starting_at_1001(self):
        if connection.vendor != "postgresql":
            self.skipTest("The sequence exists on PostgreSQL only (SQLite takes the highest number plus one).")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT start_value, min_value FROM pg_sequences WHERE sequencename = %s", [numbering.SEQUENCE]
            )
            self.assertEqual(cursor.fetchone(), (1001, 1001))

    def test_without_a_sequence_the_highest_number_plus_one_is_used(self):
        highest = new_ticket()
        with patch.object(numbering.connection, "vendor", "sqlite"):
            self.assertEqual(numbering.next_number(), highest.number + 1)

    def test_a_number_taken_meanwhile_is_skipped(self):
        taken = new_ticket()
        free = taken.number + 1
        with patch.object(numbering, "next_number", side_effect=[taken.number, free]):
            self.assertEqual(new_ticket().number, free)

    def test_creation_gives_up_after_its_attempts(self):
        taken = new_ticket()
        with patch.object(numbering, "next_number", return_value=taken.number), self.assertRaises(IntegrityError):
            new_ticket()

    def test_numbers_typed_by_staff_and_subject_tokens(self):
        for typed in ("1234", "#1234", "I2G-#1234", " [i2g-#1234] "):
            with self.subTest(typed):
                self.assertEqual(numbering.parse_number(typed), 1234)
        self.assertIsNone(numbering.parse_number("pat@example.org"))
        self.assertEqual(numbering.subject_numbers("Re: [I2G-#1002] and I2G-#1003 and [I2G-#1002]"), [1002, 1003])
        self.assertEqual(numbering.display(1005), "I2G-#1005")


class SequenceResetTests(TransactionTestCase):
    """Django resets column-owned sequences to 1 for ``reset_sequences`` tests; the ticket sequence is not one, so
    such a reset neither fails nor hands out a number below 1001."""

    reset_sequences = True

    def test_resetting_the_databases_sequences_leaves_ticket_numbers_alone(self):
        self.assertGreaterEqual(new_ticket().number, numbering.FIRST_NUMBER)
