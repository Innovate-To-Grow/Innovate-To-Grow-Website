from decimal import Decimal

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.utils.html import escape

from apps.core.admin.request_limits.forms import MANUAL_LIMIT_NOTE, RequestLimitPolicyForm, show
from apps.core.models import RequestRateLimitPolicy
from apps.core.models.base.site_controls.request_limits import MANUAL_LIMIT_HELP, SMART_LIMIT_HELP

from .helpers import RequestLimitsAdminTestCase


class AuditTests(RequestLimitsAdminTestCase):
    def entries(self):
        return list(LogEntry.objects.order_by("action_time", "id"))

    def test_each_changed_scope_leaves_one_line_with_who_and_before_after(self):
        self.client.post(
            self.url,
            self.post_data(
                **{
                    "auth-code-send-tier": "p1",
                    "auth-code-send-smart_enabled": None,
                    "auth-code-send-manual_requests": "20",
                    "ai-smart_floor": "0.2",
                    "ai-identity_ceiling": "350",
                    "view-code-send-sms-enabled": None,
                }
            ),
        )

        entries = self.entries()
        lines = sorted(entry.change_message for entry in entries)
        self.assertEqual(
            lines,
            [
                "ai: Smart floor 0.1→0.2; per-caller ceiling blank→350",
                "auth-code-send: priority P0→P1; Smart limit on→off; manual 10→20",
                "view-code-send-sms: enabled on→off",
            ],
        )
        content_type = ContentType.objects.get_for_model(RequestRateLimitPolicy)
        for entry in entries:
            with self.subTest(line=entry.change_message):
                self.assertEqual(entry.user_id, self.staff.pk)
                self.assertEqual(entry.action_flag, CHANGE)
                self.assertEqual(entry.content_type_id, content_type.pk)
                scope = entry.change_message.split(":")[0]
                self.assertEqual(entry.object_id, str(self.policy(scope).pk))

    def test_period_fixed_and_cap_changes_are_named(self):
        self.client.post(
            self.url,
            self.post_data(
                **{
                    "public-read-period_seconds": "30",
                    "public-read-fixed": "on",
                    "public-read-global_cap": "11000",
                }
            ),
        )

        self.assertEqual(
            [entry.change_message for entry in self.entries()],
            ["public-read: period (s) 60→30; fixed off→on; everyone together 12,000→11,000"],
        )

    def test_a_refused_save_writes_no_line(self):
        self.client.post(self.url, self.post_data(**{"ai-manual_requests": "0", "public-read-tier": "p3"}))
        self.assertFalse(LogEntry.objects.exists())

    def test_show_formats_values(self):
        self.assertEqual(show("tier", "p2"), "P2")
        self.assertEqual(show("fixed", True), "on")
        self.assertEqual(show("identity_ceiling", None), "blank")
        self.assertEqual(show("smart_floor", Decimal("0.500")), "0.5")
        self.assertEqual(show("manual_requests", 12_000), "12,000")
        self.assertEqual(show("label", "x"), "x")


class CardFieldTests(RequestLimitsAdminTestCase):
    def test_every_card_shows_the_exact_smart_and_manual_help(self):
        response = self.client.get(self.url)
        count = RequestRateLimitPolicy.objects.count()

        self.assertEqual(count, 51)
        self.assertContains(response, '<article id="limit-card-', count=count)
        self.assertContains(response, escape(SMART_LIMIT_HELP), count=count)
        self.assertContains(response, escape(MANUAL_LIMIT_HELP), count=count)

    def test_the_manual_limit_is_read_only_while_smart_limit_is_on(self):
        self.set_policy("ai", smart_enabled=False)
        response = self.client.get(self.url)

        self.assertTrue(self.card(response, "public-read").manual_locked)
        self.assertIn("readonly", self.card_html(response, "public-read"))
        self.assertIn(escape(str(MANUAL_LIMIT_NOTE)), self.card_html(response, "public-read"))
        self.assertFalse(self.card(response, "ai").manual_locked)
        html = self.card_html(response, "ai")
        self.assertIn("data-limit-manual-note hidden", html)

    def test_tier_help_names_the_default_and_warns_for_p0(self):
        form = RequestLimitPolicyForm(instance=self.policy("auth-code-send"), prefix="x")
        self.assertIn(
            "Default: P0 critical. In a lower tier Smart limit may tighten it under load.", form["tier"].help_text
        )
        form = RequestLimitPolicyForm(instance=self.policy("ai"), prefix="x")
        self.assertTrue(form["tier"].help_text.endswith("Default: P3 heavy."))

    def test_floor_and_ceiling_help_show_the_numbers(self):
        form = RequestLimitPolicyForm(instance=self.policy("ai"), prefix="x")
        self.assertIn(
            "A share of the baseline (300 requests per period, from REQUEST_RATE_LIMITS), so at most 1: now 30 per "
            "period at the floor (never below 1).",
            form["smart_floor"].help_text,
        )
        self.assertIn("At most 600 (deployment): it can be lowered here.", form["global_cap"].help_text)
        form = RequestLimitPolicyForm(instance=self.policy("view-assistant-chat"), prefix="x")
        self.assertIn("now 1 per period at the floor", form["smart_floor"].help_text)
        self.assertEqual(form.initial["smart_floor"], "0.1")
        self.assertEqual(form.fields["manual_requests"].widget.attrs["suffix"], "requests / 60 s")
