"""Editing on Site Settings → Request Limits: what is saved, the validation errors (each on its field, nothing saved
when any card is invalid), the manual limit kept while Smart limit is on, and the audit line of every change."""

from decimal import Decimal

from django.contrib.admin.models import LogEntry
from django.test import override_settings
from django.utils.html import escape

from apps.core.admin.request_limits.forms import RequestLimitPolicyForm
from apps.core.services.request_limits.runtime import registry
from apps.core.services.request_limits.view_limits import view_rate

from .helpers import RequestLimitsAdminTestCase


class SaveTests(RequestLimitsAdminTestCase):
    def test_every_field_of_a_card_is_saved(self):
        response = self.client.post(
            self.url,
            self.post_data(
                **{
                    "member-send-tier": "p2",
                    "member-send-smart_enabled": None,
                    "member-send-manual_requests": "7",
                    "member-send-period_seconds": "120",
                    "member-send-smart_floor": "0.25",
                    "member-send-fixed": "on",
                    "member-send-enabled": None,
                    "member-send-identity_ceiling": "8",
                    "member-send-global_cap": "250",
                }
            ),
        )

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        policy = self.policy("member-send")
        self.assertEqual(
            (
                policy.tier,
                policy.smart_enabled,
                policy.manual_requests,
                policy.period_seconds,
                policy.smart_floor,
                policy.fixed,
                policy.enabled,
                policy.identity_ceiling,
                policy.global_cap,
            ),
            ("p2", False, 7, 120, Decimal("0.250"), True, False, 8, 250),
        )
        messages = [str(message) for message in response.wsgi_request._messages]
        self.assertEqual(messages, ["Request limits saved. Every web process applies them within seconds."])

    def test_an_unchanged_page_saves_nothing(self):
        updated = {scope: self.policy(scope).updated_at for scope in ("auth-code-send", "ai")}

        response = self.client.post(self.url, self.post_data(), follow=True)

        self.assertContains(response, "No request limits changed.")
        self.assertFalse(LogEntry.objects.exists())
        for scope, moment in updated.items():
            self.assertEqual(self.policy(scope).updated_at, moment)

    def test_the_manual_limit_is_kept_and_stored_while_smart_limit_is_on(self):
        self.client.post(self.url, self.post_data(**{"ai-manual_requests": "40"}))
        policy = self.policy("ai")
        self.assertEqual((policy.smart_enabled, policy.manual_requests), (True, 40))

        self.client.post(self.url, self.post_data(**{"ai-smart_enabled": None}))
        policy = self.policy("ai")
        self.assertEqual((policy.smart_enabled, policy.manual_requests), (False, 40))

    def test_a_per_view_limit_has_no_aggregate_cap_field(self):
        form = RequestLimitPolicyForm(instance=self.policy("view-code-send-sms"), prefix="view-code-send-sms")
        self.assertNotIn("global_cap", form.fields)
        self.assertIn("global_cap", RequestLimitPolicyForm(instance=self.policy("ai"), prefix="ai").fields)

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=True)
    def test_a_saved_limit_applies_after_the_commit(self):
        self.assertEqual(view_rate("view-code-send-sms").requests, 5)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                self.url,
                self.post_data(**{"view-code-send-sms-smart_enabled": None, "view-code-send-sms-manual_requests": "2"}),
            )

        self.assertIsNone(registry.REGISTRY.loaded_at)
        self.assertEqual(view_rate("view-code-send-sms").requests, 2)


class ValidationTests(RequestLimitsAdminTestCase):
    def assert_refused(self, field, value, message, scope="ai"):
        before = {name: getattr(self.policy(scope), name) for name in RequestLimitPolicyForm.Meta.fields}
        # A valid change on another card is not saved either: the page is saved together or not at all.
        response = self.client.post(
            self.url, self.post_data(**{f"{scope}-{field}": value, "public-read-manual_requests": "2000"})
        )

        self.assertEqual(response.status_code, 200)
        card = self.card(response, scope)
        self.assertIn(message, card.form.errors[field][0])
        self.assertIn(escape(message), self.card_html(response, scope))
        self.assertContains(response, "The request limits were not saved. Please correct the errors below.")
        after = {name: getattr(self.policy(scope), name) for name in RequestLimitPolicyForm.Meta.fields}
        self.assertEqual(after, before)
        self.assertEqual(self.policy("public-read").manual_requests, 3_000)
        self.assertFalse(LogEntry.objects.exists())
        return response

    def test_limits_must_be_positive_whole_numbers(self):
        cases = (
            ("manual_requests", "0", "Ensure this value is greater than or equal to 1."),
            ("manual_requests", "-5", "Ensure this value is greater than or equal to 0."),
            ("manual_requests", "ten", "Enter a whole number."),
            ("manual_requests", "", "This field is required."),
            ("period_seconds", "0", "Ensure this value is greater than or equal to 1."),
            ("period_seconds", "86401", "Ensure this value is less than or equal to 86400."),
            ("identity_ceiling", "0", "Ensure this value is greater than or equal to 1."),
            ("global_cap", "0", "Ensure this value is greater than or equal to 1."),
        )
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                self.assert_refused(field, value, message)

    def test_the_smart_floor_is_a_share_of_the_baseline_at_most_one(self):
        for value, message in (
            ("1.5", "Ensure this value is less than or equal to 1."),
            ("0", "Ensure this value is greater than or equal to 0.001."),
            ("-0.1", "Ensure this value is greater than or equal to 0.001."),
            ("0.0001", "Ensure that there are no more than 3 decimal places."),
            ("half", "Enter a number."),
        ):
            with self.subTest(value=value):
                self.assert_refused("smart_floor", value, message)

    def test_the_manual_limit_cannot_exceed_the_per_caller_ceiling(self):
        self.set_policy("ai", identity_ceiling=50)
        response = self.assert_refused("manual_requests", "51", "It cannot be set above the per-caller ceiling of 50.")
        # An error unlocks the manual limit so it can be fixed, also while Smart limit is on.
        self.assertFalse(self.card(response, "ai").manual_locked)

    def test_a_deployment_ceiling_can_be_lowered_not_raised_or_cleared(self):
        message = "The deployment allows at most 600. It can be lowered here, not raised."
        self.assert_refused("global_cap", "601", message)
        self.assert_refused("global_cap", "", message)

        self.client.post(self.url, self.post_data(**{"ai-global_cap": "400"}))
        self.assertEqual(self.policy("ai").global_cap, 400)

    def test_an_unknown_tier_is_refused(self):
        self.assert_refused("tier", "p9", "Select a valid choice. p9 is not one of the available choices.")

    def test_a_rejected_card_stays_in_its_stored_tier(self):
        response = self.assert_refused("manual_requests", "0", "greater than or equal to 1", scope="public-heavy")
        response = self.client.post(
            self.url, self.post_data(**{"public-heavy-tier": "p1", "public-heavy-manual_requests": "0"})
        )
        p3 = next(group for group in response.context["groups"] if group["tier"] == "p3")
        self.assertIn("public-heavy", [card.scope for card in p3["routes"]])
