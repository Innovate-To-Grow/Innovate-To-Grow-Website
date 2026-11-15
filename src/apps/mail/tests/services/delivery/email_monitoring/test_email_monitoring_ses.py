"""Email Monitoring → Amazon SES: how the Delivery Dashboard payload is shaped for the tab (no AWS, no database)."""

from django.test import SimpleTestCase

from apps.mail.services.email_monitoring import ses


def _row(email, reason="BOUNCE"):
    return {"email": email, "reason": reason, "status": "bounced", "label": "Bounced", "source": "", "context": ""}


class WindowTests(SimpleTestCase):
    def test_only_the_four_ranges_are_accepted(self):
        for value, days in (("7", 7), ("90", 90), ("183", 183), ("365", 365), ("30", 183), ("x", 183), (None, 183)):
            with self.subTest(value=value):
                self.assertEqual(ses.window_days({} if value is None else {"days": value}), days)

    def test_the_options_mark_the_chosen_range(self):
        options = ses.window_options(90)

        self.assertEqual([option["days"] for option in options], [7, 90, 183, 365])
        self.assertEqual([option["short"] for option in options if option["selected"]], ["3mo"])
        self.assertEqual(ses.window(12)["label"], "Last 6 months")


class FigureTests(SimpleTestCase):
    def test_the_error_types_are_ranked_against_the_largest(self):
        rows = ses.error_types({"bounces": 4, "complaints": 1, "rejected": 2})

        self.assertEqual(
            [(row["key"], row["count"], row["share"]) for row in rows][:3],
            [
                ("bounces", 4, 100.0),
                ("complaints", 1, 25.0),
                ("rejected", 2, 50.0),
            ],
        )
        self.assertEqual(rows[3], {"key": "failed", "label": "Rendering failures", "count": 0, "share": 0.0})
        self.assertTrue(all(row["share"] == 0 for row in ses.error_types({})))

    def test_the_daily_series_keeps_every_day_and_tables_the_active_ones(self):
        series = ses.daily_series(
            [{"date": "2026-01-30", "attempts": 0, "problems": 0}, {"date": "2026-01-31", "attempts": 9, "problems": 1}]
        )

        self.assertEqual(series["display"], ["Jan 30", "Jan 31"])
        self.assertEqual(series["series"], {"attempts": [0, 9], "problems": [0, 1]})
        self.assertEqual(series["table"], [{"label": "Jan 31", "values": [9, 1]}])
        self.assertEqual(ses.daily_series([])["labels"], [])


class RecipientTests(SimpleTestCase):
    def payload(self, rows, **details):
        return {
            "problem_recipients": rows,
            "recipient_details": {"available": True, "reason": "", **details},
            "aws": {},
        }

    def test_domains_and_counts_come_from_the_rows_when_aws_gives_no_totals(self):
        rows = [_row("A@Example.COM"), _row("b@example.org", "COMPLAINT"), _row("not-an-address")]

        found = ses.recipients(self.payload(rows), ses.window(7))

        self.assertEqual([row["domain"] for row in found["rows"]], ["example.com", "example.org", "-"])
        self.assertEqual((found["total"], found["bounced"], found["complained"]), (3, 2, 1))
        self.assertEqual(found["latest"], "-")
        self.assertNotIn("domain", rows[0])  # the payload itself (also the JSON) is left as it is

    def test_aws_totals_win_over_the_rows_shown(self):
        found = ses.recipients(
            self.payload([_row("a@example.com")], total_count=40, reason_counts={"BOUNCE": 30, "COMPLAINT": 10}),
            ses.window(183),
        )

        self.assertEqual((found["total"], found["bounced"], found["complained"]), (40, 30, 10))
        self.assertEqual(found["empty"], "No suppressed recipient addresses found in AWS SES for last 6 months.")
