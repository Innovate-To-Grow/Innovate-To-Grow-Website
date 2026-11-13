"""A bounce report whose server says the person left the organisation (an organisation's rule refusing a departed
employee's mail) is a disabled mailbox: the address no longer reaches them. Only generic codes are refined: a
specific code still decides, a temporary code stays temporary, and a sender-side "no longer valid" stays a policy
refusal. Pure: no database."""

from django.test import SimpleTestCase

from apps.core.models import EmailBounce
from apps.core.services.email.bounces.classify import classify

Category = EmailBounce.Category
LEFT = "The recipient's server says the person left the organisation or the address was retired"


class LeftOrganisationReportTests(SimpleTestCase):
    def test_a_rejection_saying_the_person_left_is_a_disabled_mailbox(self):
        for status, diagnostic in (
            ("5.7.1", "550 5.7.1 Jordan Park is no longer with Contoso. Please contact info@contoso.example"),
            ("5.0.0", "554 5.0.0 This user has left the company"),
            ("", "550 Recipient address is no longer valid"),
            ("5.7.1", "550 5.7.1 Mailbox has been retired"),
            ("5.0.0", "550 5.0.0 Taylor no longer works for Fabrikam"),
        ):
            with self.subTest(diagnostic):
                verdict = classify("failed", status, diagnostic)
                self.assertEqual(
                    (verdict.category, verdict.classification, verdict.is_permanent, verdict.reason),
                    (Category.MAILBOX_DISABLED, "hard", True, LEFT),
                )

    def test_a_specific_code_still_decides(self):
        self.assertEqual(
            classify("failed", "5.1.1", "550 5.1.1 no longer with us; user unknown").category, Category.HARD
        )

    def test_a_temporary_code_is_never_evidence_against_the_address(self):
        verdict = classify("failed", "4.0.0", "450 4.0.0 Jordan no longer works here, try again later")

        self.assertEqual((verdict.category, verdict.is_permanent), (Category.TRANSIENT, False))

    def test_our_own_credentials_no_longer_valid_stay_a_policy_refusal(self):
        verdict = classify("failed", "5.7.1", "550 5.7.1 Your sender certificate is no longer valid")

        self.assertEqual(verdict.category, Category.POLICY_REJECTED)
