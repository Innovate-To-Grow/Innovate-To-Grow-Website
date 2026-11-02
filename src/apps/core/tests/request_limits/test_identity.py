"""Who a request counts against: members verified offline from their JWT (never from unverified claims), the admin
session user, the CLI token, the client IP, and app-registered destinations."""

import hashlib
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.core.services.request_limits import identity, register_identity_resolver

from .helpers import isolate

Member = get_user_model()


def _bearer(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class IdentityTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        self.factory = RequestFactory()
        self.member = Member.objects.create_user(email="limits@example.com", password="pw-123456!", is_active=True)

    def test_a_valid_access_token_is_verified_offline(self):
        request = self.factory.get("/news/", **_bearer(RefreshToken.for_user(self.member).access_token))
        with self.assertNumQueries(0):
            found = identity.resolve(request)
        self.assertEqual(found.member, str(self.member.pk))
        self.assertEqual(found.person, f"u:{self.member.pk}")
        self.assertIs(identity.resolve(request), found)  # once per request

    def test_unverifiable_tokens_are_never_trusted(self):
        expired = AccessToken.for_user(self.member)
        expired.set_exp(lifetime=-timedelta(seconds=5))
        forged = jwt.encode(
            {"member_uuid": str(self.member.pk), "token_type": "access", "aud": "i2g-api", "iss": "i2g-backend"},
            "not-the-signing-key-but-long-enough-for-hs256",
            algorithm="HS256",
        )
        refresh = RefreshToken.for_user(self.member)
        for name, token in (("expired", expired), ("forged", forged), ("refresh", refresh), ("junk", "abc")):
            with self.subTest(name):
                found = identity.resolve(self.factory.get("/news/", **_bearer(token)))
                self.assertIsNone(found.member)
                self.assertIsNone(found.cli)

    def test_a_token_without_the_member_claim_is_nobody(self):
        token = AccessToken.for_user(self.member)
        del token.payload[settings.SIMPLE_JWT["USER_ID_CLAIM"]]
        self.assertIsNone(identity.resolve(self.factory.get("/", **_bearer(token))).member)

    def test_malformed_headers_are_ignored(self):
        for header in ("Bearer", "Basic abc", "Bearer a b", "Token abc"):
            with self.subTest(header=header):
                found = identity.resolve(self.factory.get("/", HTTP_AUTHORIZATION=header))
                self.assertEqual((found.member, found.cli), (None, None))

    def test_the_session_user_counts_only_with_a_session_cookie(self):
        request = self.factory.get("/admin/")
        request.user = self.member
        self.assertIsNone(identity.resolve(request).user)
        request = self.factory.get("/admin/")
        request.COOKIES[settings.SESSION_COOKIE_NAME] = "session"
        request.user = self.member
        self.assertEqual(identity.resolve(request).user, str(self.member.pk))
        anonymous = self.factory.get("/admin/")
        anonymous.COOKIES[settings.SESSION_COOKIE_NAME] = "session"
        anonymous.user = AnonymousUser()
        self.assertIsNone(identity.resolve(anonymous).user)
        bare = self.factory.get("/admin/")
        bare.COOKIES[settings.SESSION_COOKIE_NAME] = "session"
        self.assertIsNone(identity.resolve(bare).user)

    def test_a_cli_token_counts_by_its_hash_only_under_the_cli_prefix(self):
        found = identity.resolve(self.factory.get("/admin-api/whoami/", **_bearer("cli-token")))
        self.assertEqual(found.cli, hashlib.sha256(b"cli-token").hexdigest())
        self.assertIsNone(identity.resolve(self.factory.get("/news/", **_bearer("cli-token"))).cli)

    @override_settings(NUM_PROXIES=1)
    def test_the_client_ip_honours_the_trusted_proxies(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 1.2.3.4", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(identity.resolve(request).ip, "1.2.3.4")
        no_ip = self.factory.get("/", REMOTE_ADDR="")
        self.assertIsNone(identity.resolve(no_ip).ip)


class KeyTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)

    def test_keys_per_kind(self):
        member = identity.Identity(member="m", ip="1.1.1.1")
        staff = identity.Identity(user="s", ip="1.1.1.1")
        cli = identity.Identity(cli="h", ip="1.1.1.1")
        anonymous = identity.Identity(ip="1.1.1.1")
        nobody = identity.Identity()
        table = {
            "member": ("u:m", "u:s", None, None, None),
            "session": (None, "u:s", None, None, None),
            "cli": ("u:m", "u:s", "c:h", None, None),
            "ip": ("u:m", "u:s", "c:h", "ip:1.1.1.1", None),
            "destination": ("u:m", "u:s", None, None, None),
            "global": (None, None, None, None, None),
        }
        for kind, expected in table.items():
            with self.subTest(kind=kind):
                self.assertEqual(tuple(who.key(kind) for who in (member, staff, cli, anonymous, nobody)), expected)
        self.assertEqual(anonymous.key("destination", "abc"), "d:abc")

    def test_a_registered_destination_resolver_keys_the_scope(self):
        factory = RequestFactory()
        register_identity_resolver("auth-code-send", lambda request: request.GET.get("phone"))
        key = identity.bucket_key(factory.get("/?phone=+15550001"), "auth-code-send", "destination")
        self.assertTrue(key.startswith("d:"))
        self.assertNotIn("15550001", key)
        self.assertEqual(identity.bucket_key(factory.get("/?phone=+15550001"), "auth-code-send", "destination"), key)
        self.assertIsNone(identity.bucket_key(factory.get("/"), "auth-code-send", "destination"))
        self.assertIsNone(identity.bucket_key(factory.get("/"), "auth-sign-in", "destination"))

    def test_a_resolver_by_dotted_path_and_a_failing_one(self):
        factory = RequestFactory()
        register_identity_resolver("auth-sign-in", "apps.core.tests.request_limits.test_identity.path_resolver")
        self.assertTrue(identity.bucket_key(factory.get("/x/"), "auth-sign-in", "destination").startswith("d:"))

        def explode(request):
            raise RuntimeError("bad")

        register_identity_resolver("auth-sign-in", explode)
        with self.assertLogs("apps.core.services.request_limits.identity", "WARNING"):
            self.assertIsNone(identity.bucket_key(factory.get("/x/"), "auth-sign-in", "destination"))


def path_resolver(request):
    return request.path
