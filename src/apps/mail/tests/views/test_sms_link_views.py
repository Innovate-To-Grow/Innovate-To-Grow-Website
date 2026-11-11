"""``POST /mail/sms-link/`` (the SPA's /l/<token>) and ``GET /mail/register-link/`` (the SPA's /register)."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.event.tests.helpers import make_member
from apps.mail.models import SmsCampaign, SmsConfig, SmsLinkToken
from apps.mail.services.sms import links
from apps.mail.services.sms.register_link import CACHE_KEY

from ..services.sms.policy_helpers import add_phone

LINK_URL = "/mail/sms-link/"
REGISTER_URL = "/mail/register-link/"


def token_of(url):
    return url.rsplit("/l/", 1)[1]


@override_settings(FRONTEND_URL="https://i2g.example.edu")
class SmsLinkViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = make_member(email="ada@example.com", first_name="Ada", last_name="Lovelace")
        add_phone(self.member, "2095550101")

    def personal(self, redirect_path="/subscribe"):
        return token_of(
            links.issue_personal_link(
                purpose=links.Purpose.LOGIN,
                member=self.member,
                phone="+12095550101",
                redirect_path=redirect_path,
                validity_days=3,
            )
        )

    def test_a_personal_link_signs_in_once_and_says_where_to_go(self):
        token = self.personal()
        with self.assertLogs("apps.mail.views.sms_link", level="INFO") as logs:
            response = self.client.post(LINK_URL, {"token": token}, format="json")
            again = self.client.post(LINK_URL, {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["kind"], response.data["redirect_to"]), ("sign_in", "/subscribe"))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(again["Cache-Control"], "no-store")
        self.assertTrue(response.data["access"] and response.data["refresh"])
        self.assertEqual(response.data["user"]["email"], "ada@example.com")
        self.assertEqual(again.status_code, 400)
        self.assertEqual((again.data["code"], again.data["redirect_to"]), ("already_used", "/subscribe"))
        self.assertNotIn(token, "\n".join(logs.output))

    def test_a_stale_bearer_header_never_turns_it_into_a_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        response = self.client.post(LINK_URL, {"token": self.personal()}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_a_shared_link_answers_a_redirect_without_signing_in(self):
        campaign = SmsCampaign.objects.create(message="{{event_link}}", audience_type="all_members")
        token = token_of(
            links.shared_link(
                campaign=campaign,
                purpose=links.Purpose.EVENT,
                redirect_path="/event-registration?event=x",
                validity_days=3,
            )
        )
        response = self.client.post(LINK_URL, {"token": token}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"kind": "redirect", "redirect_to": "/event-registration?event=x"})

    def test_an_expired_link_is_refused_with_its_destination(self):
        token = self.personal("/account")
        SmsLinkToken.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        response = self.client.post(LINK_URL, {"token": token}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data, {"detail": "This link has expired.", "code": "expired", "redirect_to": "/account"}
        )

    def test_missing_unknown_and_malformed_tokens_reveal_nothing(self):
        for body, code in (
            ({}, "token_required"),
            ({"token": ["x"]}, "token_required"),
            ({"token": "A" * 22}, "invalid_link"),
            ({"token": "<script>"}, "invalid_link"),
        ):
            with self.subTest(body=body):
                response = self.client.post(LINK_URL, body, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["code"], code)
                self.assertNotIn("redirect_to", response.data)

    def test_only_post_is_allowed(self):
        self.assertEqual(self.client.get(LINK_URL).status_code, 405)


class RegisterLinkViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()

    def test_by_default_register_leads_to_the_sign_in_page(self):
        response = self.client.get(REGISTER_URL)
        self.assertEqual((response.status_code, response.data), (200, {"path": "/login"}))

    def test_staff_choose_the_page_and_a_save_takes_effect_at_once(self):
        self.client.get(REGISTER_URL)  # cached
        config = SmsConfig.load()
        config.register_redirect_path = "/event-registration?event=fall-demo"
        with self.captureOnCommitCallbacks(execute=True):
            config.save()
        self.assertIsNone(cache.get(CACHE_KEY))
        self.assertEqual(self.client.get(REGISTER_URL).data, {"path": "/event-registration?event=fall-demo"})

    def test_a_stored_value_that_is_not_a_safe_page_falls_back(self):
        for stored in ("//evil.example", "/\\evil.example", "/register", "/register/?x=1", "https://evil.example"):
            with self.subTest(stored=stored):
                cache.clear()
                SmsConfig.objects.filter(pk=SmsConfig.load().pk).update(register_redirect_path=stored)
                self.assertEqual(self.client.get(REGISTER_URL).data, {"path": "/login"})
