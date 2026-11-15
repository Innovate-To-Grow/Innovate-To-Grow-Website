"""Per-member limits on the signed-in account views: the code checks that used to be a no-op (an anonymous
throttle on login-only views) now count per member, change-password and adding contact phones are bounded, and
every rate is a live request-limit policy."""

import uuid

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.authn.models import Member
from apps.authn.security.throttles import (
    ChangePasswordThrottle,
    ContactEmailCreateThrottle,
    ContactPhoneCreateThrottle,
    EmailCodeVerifyThrottle,
)
from apps.core.models import RequestRateLimitPolicy
from apps.core.services.request_limits.runtime import registry
from apps.core.services.request_limits.view_limits import MemberRateThrottle
from apps.core.tests.request_limits.helpers import isolate, view_limit

VERIFY_PATHS = (
    "/authn/change-password/verify-code/",
    "/authn/change-password/confirm/",
    "/authn/delete-account/verify-code/",
    "/authn/delete-account/confirm/",
    f"/authn/contact-emails/{uuid.uuid4()}/verify-code/",
    f"/authn/contact-phones/{uuid.uuid4()}/verify-code/",
    "/event/verify-phone-code/",
    "/event/verify-secondary-email-code/",
)


class MemberThrottleTestCase(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        self.member = Member.objects.create_user(email="limits@example.com", password="Pass-123456!", is_active=True)
        self.client = APIClient()
        self.client.force_authenticate(self.member)

    def other_client(self):
        other = Member.objects.create_user(email=f"{uuid.uuid4().hex}@example.com", password="x", is_active=True)
        client = APIClient()
        client.force_authenticate(other)
        return client


@view_limit(**{"view-code-verify": (2, 60)})
class CodeCheckThrottleTests(MemberThrottleTestCase):
    def test_every_signed_in_code_check_is_limited_per_member(self):
        for path in VERIFY_PATHS:
            with self.subTest(path=path):
                cache.clear()
                statuses = [self.client.post(path, {}, format="json").status_code for _ in range(3)]
                self.assertNotIn(429, statuses[:2])
                self.assertEqual(statuses[2], 429)

    def test_one_bucket_per_member_across_the_code_checks(self):
        self.client.post(VERIFY_PATHS[0], {}, format="json")
        self.client.post(VERIFY_PATHS[6], {}, format="json")
        self.assertEqual(self.client.post(VERIFY_PATHS[2], {}, format="json").status_code, 429)
        # Another member has a bucket of their own.
        self.assertNotEqual(self.other_client().post(VERIFY_PATHS[0], {}, format="json").status_code, 429)

    def test_anonymous_callers_get_the_login_answer_not_a_shared_ip_bucket(self):
        anonymous = APIClient()
        statuses = {anonymous.post(VERIFY_PATHS[0], {}, format="json").status_code for _ in range(5)}
        self.assertEqual(statuses, {401})

    def test_the_throttle_counts_per_member_never_per_ip(self):
        self.assertTrue(issubclass(EmailCodeVerifyThrottle, MemberRateThrottle))
        self.assertEqual(EmailCodeVerifyThrottle.policy_scope, "view-code-verify")


@view_limit(**{"view-change-password": (2, 3600)})
class ChangePasswordThrottleTests(MemberThrottleTestCase):
    def test_password_guesses_are_bounded_per_member(self):
        statuses = [self.client.post("/authn/change-password/", {}, format="json").status_code for _ in range(3)]
        self.assertEqual(statuses, [400, 400, 429])
        self.assertEqual(self.other_client().post("/authn/change-password/", {}, format="json").status_code, 400)


@view_limit(**{"view-contact-phone-create": (2, 3600)})
class ContactPhoneCreateThrottleTests(MemberThrottleTestCase):
    def test_adding_phones_is_bounded_like_adding_emails(self):
        statuses = [self.client.post("/authn/contact-phones/", {}, format="json").status_code for _ in range(3)]
        self.assertEqual(statuses, [400, 400, 429])

    def test_listing_phones_is_not(self):
        statuses = {self.client.get("/authn/contact-phones/").status_code for _ in range(5)}
        self.assertEqual(statuses, {200})


class DefaultRateTests(TestCase):
    def test_the_new_limits_default_to_ten_and_five_an_hour(self):
        self.assertEqual((ChangePasswordThrottle().num_requests, ChangePasswordThrottle().duration), (10, 3600))
        # Adding a phone mirrors adding an email.
        phone, email = ContactPhoneCreateThrottle(), ContactEmailCreateThrottle()
        self.assertEqual((phone.num_requests, phone.duration), (email.num_requests, email.duration))
        self.assertEqual((phone.num_requests, phone.duration), (5, 3600))


@override_settings(REQUEST_RATE_LIMITS_ENABLED=True)
class LivePolicyTests(MemberThrottleTestCase):
    def test_an_admin_change_applies_without_a_restart(self):
        path = "/authn/change-password/"
        self.assertEqual({self.client.post(path, {}, format="json").status_code for _ in range(3)}, {400})
        policy = RequestRateLimitPolicy.for_scope("view-change-password")
        policy.smart_enabled, policy.manual_requests = False, 3
        with self.captureOnCommitCallbacks(execute=True):
            policy.save()
        self.assertEqual(self.client.post(path, {}, format="json").status_code, 429)

    def test_switching_a_policy_off_lifts_its_limit(self):
        RequestRateLimitPolicy.objects.filter(scope="view-contact-phone-create").update(enabled=False)
        registry.invalidate()
        statuses = {self.client.post("/authn/contact-phones/", {}, format="json").status_code for _ in range(7)}
        self.assertEqual(statuses, {400})
