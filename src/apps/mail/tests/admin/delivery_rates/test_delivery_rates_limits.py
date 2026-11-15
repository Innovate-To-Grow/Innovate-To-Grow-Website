"""Mail → Delivery Rates: the SES limit carried over from the old campaign send rate gives way to the one AWS
reports, until staff make it their own; and mail staff cannot raise Google's external-recipient limit by naming an
internal domain."""

from decimal import Decimal

from apps.core.tests.gmail_api_helpers import make_config

from .delivery_rates_helpers import READ_AT, Channel, DeliveryRatesTestCase


class CarriedOverSesLimitTests(DeliveryRatesTestCase):
    def setUp(self):
        super().setUp()
        self.set_policy(
            Channel.SES_SEND, provider_limit=Decimal(10), manual_rate=Decimal(10), provider_limit_carried_over=True
        )

    def test_the_field_says_it_applies_only_until_aws_reports_the_limit(self):
        html = self.card_html(self.client.get(self.url), Channel.SES_SEND)

        self.assertIn("Carried over from the old campaign send rate: it applies only until AWS reports", html)
        self.assertIn("(the old campaign send rate, until AWS reports the account&#x27;s limit)", html)

    def test_once_aws_reports_its_limit_the_card_says_the_carried_over_one_no_longer_applies(self):
        self.state(Channel.SES_SEND, self.ses_identity, discovered_rate=14.0, discovered_at=READ_AT)

        html = self.card_html(self.client.get(self.url), Channel.SES_SEND)

        self.assertIn("Provider limit: 14 recipients/sec (reported by AWS 5 min ago)", html)
        self.assertIn("no longer applies: AWS reports 14 recipients/sec. Clear it, or enter your own limit.", html)

    def test_saving_the_page_unchanged_keeps_it_carried_over(self):
        self.client.post(self.url, self.post_data(**{"graph_send-manual_rate": "20"}))

        self.assertTrue(self.policy(Channel.SES_SEND).provider_limit_carried_over)

    def test_entering_a_limit_makes_it_the_operators(self):
        self.client.post(self.url, self.post_data(**{"ses_send-provider_limit": "12", "ses_send-manual_rate": "12"}))

        policy = self.policy(Channel.SES_SEND)
        self.assertEqual(policy.provider_limit, Decimal(12))
        self.assertFalse(policy.provider_limit_carried_over)
        self.assertNotIn("Carried over from", self.card_html(self.client.get(self.url), Channel.SES_SEND))

    def test_clearing_it_leaves_only_what_aws_reports(self):
        self.client.post(self.url, self.post_data(**{"ses_send-provider_limit": ""}))

        policy = self.policy(Channel.SES_SEND)
        self.assertEqual((policy.provider_limit, policy.provider_limit_carried_over), (None, False))


class InternalDomainTests(DeliveryRatesTestCase):
    """Recipients in the internal domain skip Google's 2,000 external recipients a day: naming a domain raises that
    documented limit, so only the domain of an allow-listed account (or a parent of it) may be named."""

    FIELD = "gmail_api_send-internal_domain"

    def test_mail_staff_cannot_name_a_domain_outside_the_allow_list(self):
        make_config(subjects=("i2g@g.ucmerced.edu",), active=False)

        response = self.client.post(self.url, self.post_data(**{self.FIELD: "gmail.com"}))

        errors = self.card(response, Channel.GMAIL_API_SEND).form.errors["internal_domain"]
        self.assertIn("domain of an account on a Gmail API allow-list, or a parent domain of it", errors[0])
        self.assertIn("(g.ucmerced.edu, ucmerced.edu)", errors[0])
        self.assertEqual(self.policy(Channel.GMAIL_API_SEND).internal_domain, "")

    def test_mail_staff_can_name_the_workspace_domain_of_an_allow_listed_account_and_clear_it(self):
        make_config(subjects=("i2g@g.ucmerced.edu",), active=False)

        self.client.post(self.url, self.post_data(**{self.FIELD: "ucmerced.edu"}))
        self.assertEqual(self.policy(Channel.GMAIL_API_SEND).internal_domain, "ucmerced.edu")

        self.client.post(self.url, self.post_data(**{self.FIELD: ""}))
        self.assertEqual(self.policy(Channel.GMAIL_API_SEND).internal_domain, "")

    def test_without_an_allow_list_no_domain_can_be_named(self):
        response = self.client.post(self.url, self.post_data(**{self.FIELD: "ucmerced.edu"}))

        self.assertIn(
            "No account is on a Gmail API allow-list yet",
            self.card(response, Channel.GMAIL_API_SEND).form.errors["internal_domain"][0],
        )
