"""Who a refusal is charged to, end to end: only a caller's own excess is an abuse strike, a block always ends, one
anonymous source can never fill a P0 aggregate cap for everyone, replayed proofs and made-up CLI tokens buy nothing,
and CSRF failures are counted (the review of the Smart request limits: B1, B2, M1–M3, m4)."""

import copy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import RequestRateLimitState
from apps.core.services.request_limits import priority, register_priority_check
from apps.core.services.request_limits.runtime import registry, signals

from .helpers import TEST_SCOPES, isolate, limits_with, make_scope

Member = get_user_model()
URLS = "apps.core.tests.request_limits.urls"
CAMPUS = "203.0.113.7"


def scopes_with(**changes):
    scopes = copy.deepcopy(TEST_SCOPES)
    scopes["t-p0-anon"] = {**make_scope("p0", 5, identity="destination", global_cap=10), "source_cap": 3}
    scopes["t-cli"] = {**make_scope("p1", 100, identity="cli", global_cap=1_000), "source_cap": 3}
    for name, values in changes.items():
        scopes[name] = {**scopes[name], **values}
    return scopes


def limiter(**changes):
    return override_settings(
        REQUEST_RATE_LIMITS_ENABLED=True,
        REQUEST_RATE_LIMITS=limits_with(scopes_with(**changes), fallback={"cli_prefix": "/cli/"}),
        ROOT_URLCONF=URLS,
    )


@limiter(**{"t-p1": {"requests": 30}})
class StrikeTests(TestCase):
    """B1 and M3: a shared campus IP is never blocked for good, nor for refusals that are not its own doing."""

    def setUp(self):
        cache.clear()
        self.clock = isolate(self)
        self.client = APIClient()

    def get(self, path="/p1/"):
        return self.client.get(path, REMOTE_ADDR=CAMPUS).status_code

    def test_a_campus_over_its_limit_once_is_served_again_when_the_block_ends(self):
        first = [self.get() for _ in range(40)]
        self.assertEqual(first, [200] * 30 + [429] * 10)
        later = []
        for _ in range(300):  # then one request every 4 s (half the limit) for 20 minutes
            self.clock.advance(4)
            later.append(self.get())
        # Blocked for 30 s from the tenth refusal, then over the limit for the rest of that minute, then served every
        # time: refusals during the block never lengthen it, and seven more refusals are no new block.
        self.assertEqual(later[:14], [429] * 14)
        self.assertEqual(set(later[14:]), {200})

    def test_slot_refusals_are_no_strikes(self):
        with patch.object(signals, "admit", return_value=False):
            self.assertEqual({self.get() for _ in range(20)}, {429})
        self.assertEqual(self.get(), 200)

    @limiter(**{"t-p1": {"requests": 1_000, "global_cap": 2}})
    def test_aggregate_cap_refusals_are_no_strikes(self):
        self.assertEqual([self.get() for _ in range(15)], [200, 200] + [429] * 13)
        self.clock.advance(60)
        self.assertEqual(self.get(), 200)

    def test_going_over_only_a_smart_cut_is_no_strike(self):
        registry.configs(self.clock())
        RequestRateLimitState.objects.filter(scope="t-p1").update(factor=0.5)
        registry.invalidate()
        statuses = [self.get() for _ in range(30)]
        self.assertEqual(statuses, [200] * 15 + [429] * 15)
        self.clock.advance(60)
        self.assertEqual(self.get(), 200)

    def test_the_views_own_429s_are_no_strikes_against_a_shared_ip(self):
        self.assertEqual({self.get("/p1-refused/") for _ in range(12)}, {429})
        self.assertEqual(self.get(), 200)

    def test_the_views_own_429s_still_strike_a_signed_in_person(self):
        member = Member.objects.create_user(email="strike@example.com", password="pw-123456!", is_active=True)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}")
        self.assertEqual({self.get("/p1-refused/") for _ in range(10)}, {429})
        response = self.client.get("/p1/", REMOTE_ADDR=CAMPUS)
        self.assertEqual((response.status_code, response.json()["retry_after"]), (429, 30))


@limiter()
class SourceCeilingTests(TestCase):
    """B2: one anonymous source can no longer fill a P0 aggregate cap; it is the one that gets blocked."""

    def setUp(self):
        cache.clear()
        self.clock = isolate(self)
        self.client = APIClient()

    def post(self, address):
        return self.client.post("/p0-anonymous/", REMOTE_ADDR=address).status_code

    def test_a_flooding_source_is_refused_while_everyone_else_gets_through(self):
        flood = [self.post("198.51.100.9") for _ in range(20)]
        self.assertEqual(flood, [200] * 3 + [429] * 17)
        users = [self.post(f"10.0.0.{index}") for index in range(5)]
        self.assertEqual(users, [200] * 5)

    def test_the_flooding_source_is_escalated(self):
        for _ in range(13):  # 3 served, then the tenth refusal blocks the source for 30 s
            self.post("198.51.100.9")
        self.clock.advance(10)
        response = self.client.post("/p0-anonymous/", REMOTE_ADDR="198.51.100.9")
        self.assertEqual((response.status_code, response.json()["retry_after"]), (429, 20))
        self.clock.advance(50)  # the block is over and a new window has begun
        self.assertEqual(self.post("198.51.100.9"), 200)

    def test_a_signed_in_person_never_counts_against_the_source(self):
        for _ in range(4):
            self.post(CAMPUS)
        member = Member.objects.create_user(email="source@example.com", password="pw-123456!", is_active=True)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}")
        self.assertEqual(self.post(CAMPUS), 200)

    def test_made_up_cli_tokens_share_their_source_ceiling(self):
        # M2: a fresh bearer per request no longer buys a fresh bucket.
        statuses = [
            self.client.get("/cli/", REMOTE_ADDR="198.51.100.9", HTTP_AUTHORIZATION=f"Bearer junk-{index}").status_code
            for index in range(5)
        ]
        self.assertEqual(statuses, [200] * 3 + [429] * 2)
        other = self.client.get("/cli/", REMOTE_ADDR="10.0.0.1", HTTP_AUTHORIZATION="Bearer real")
        self.assertEqual(other.status_code, 200)


@limiter()
class ProofReplayTests(TestCase):
    """M1: one solved proof promotes only a few requests; the replays are counted as unproven traffic."""

    def setUp(self):
        cache.clear()
        isolate(self)
        saved = dict(priority._CHECKS)
        priority._CHECKS.clear()
        self.addCleanup(lambda: (priority._CHECKS.clear(), priority._CHECKS.update(saved)))
        register_priority_check("t-p0", lambda request: request.headers.get("X-Proof") or False)
        register_priority_check("t-p1", lambda request: request.headers.get("X-Proof") == "ok")

    def test_a_replayed_proof_stops_being_promoted(self):
        with patch.object(signals, "admit", side_effect=lambda tier, now: True) as admit:
            for _ in range(5):
                APIClient().post("/p0/", HTTP_X_PROOF="challenge-1")
            APIClient().post("/p0/", HTTP_X_PROOF="challenge-2")
        self.assertEqual([call.args[0] for call in admit.call_args_list], ["p0"] * 3 + ["p2"] * 2 + ["p0"])

    def test_a_check_without_a_proof_id_is_not_counted(self):
        with patch.object(signals, "admit", side_effect=lambda tier, now: True) as admit:
            for _ in range(5):
                APIClient().get("/p1/", HTTP_X_PROOF="ok")
        self.assertEqual([call.args[0] for call in admit.call_args_list], ["p1"] * 5)


@limiter(**{"t-p1": {"requests": 2}})
class CsrfTests(TestCase):
    """m4: the limiter decides before CSRF, so requests refused for their CSRF token are counted too."""

    def setUp(self):
        cache.clear()
        isolate(self)

    def test_csrf_failures_are_limited(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual([client.post("/csrf/").status_code for _ in range(3)], [403, 403, 429])
