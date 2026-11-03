"""Priority-aware Smart limiting end to end ("用户主动请求的验证码应该有高的优先级"): under overload Smart sheds
P3, then P2, then P1 while P0 (sign-in, verification codes) keeps succeeding; reserved slots keep room for P0;
P0 abuse limits still fire and escalate; recovery restores P1, then P2, then P3."""

import copy

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import RequestRateLimitState
from apps.core.services.request_limits.runtime import registry, signals, smart

from .helpers import TEST_SCOPES, isolate, limiter_on

Member = get_user_model()
WINDOW = 15


def dedupe(items):
    return [item for index, item in enumerate(items) if index == 0 or items[index - 1] != item]


def factors():
    return dict(RequestRateLimitState.objects.filter(scope__startswith="t-").values_list("scope", "factor"))


SCOPES = copy.deepcopy(TEST_SCOPES)
SCOPES["t-p3"]["requests"] = 40  # 4 per round × 4 rounds a minute fits at full speed, not at the P3 floor
SCOPES["t-p0"]["requests"] = 20  # one member's code requests: 8 a minute in these rounds


@limiter_on(scopes=SCOPES)
class OverloadTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = isolate(self)
        self.client = APIClient()
        self.member = Member.objects.create_user(email="p0@example.com", password="pw-123456!", is_active=True)
        self.bearer = {"HTTP_AUTHORIZATION": f"Bearer {RefreshToken.for_user(self.member).access_token}"}

    def round(self, *, errors: int):
        """One signal window of mixed traffic (``errors`` P1 requests answer 503), then the clock moves on."""
        results = {"p0": [], "p3": []}
        for _ in range(2):
            results["p0"].append(self.client.post("/p0/", **self.bearer).status_code)
        for _ in range(14):
            self.client.get("/p1/")
        for _ in range(errors):
            self.client.get("/p1-error/")
        for _ in range(4):
            self.client.get("/p2/")
            self.client.get("/fixed/")
            results["p3"].append(self.client.get("/p3/").status_code)
        self.clock.advance(WINDOW)
        return results

    def test_overload_sheds_p3_then_p2_then_p1_while_p0_succeeds_and_recovery_runs_in_reverse(self):
        shed, p0_statuses, p3_statuses = [], [], []
        for _ in range(16):
            results = self.round(errors=3)
            p0_statuses += results["p0"]
            p3_statuses += results["p3"]
            if smart.LAST.get("action") == "shed":
                shed.append(smart.LAST["tier"])
        self.assertEqual(dedupe(shed), ["p3", "p2", "p1"])
        self.assertEqual(set(p0_statuses), {200})
        self.assertIn(429, p3_statuses)  # P3 is really refused once it is shed
        cut = factors()
        self.assertEqual((cut["t-p0"], cut["t-fixed"]), (1.0, 1.0))
        self.assertAlmostEqual(cut["t-p3"], 0.1)
        self.assertAlmostEqual(cut["t-p2"], 0.25)
        self.assertAlmostEqual(cut["t-p1"], 0.5)
        self.assertEqual(RequestRateLimitState.objects.get(scope="t-p1").last_decision["pressure"], "overload")

        restored = []
        for _ in range(40):
            self.round(errors=0)
            if smart.LAST.get("action") == "restore" and smart.LAST.get("tier"):
                restored.append(smart.LAST["tier"])
        self.assertEqual(dedupe(restored), ["p1", "p2", "p3"])
        self.assertEqual(set(factors().values()), {1.0})

    def test_p0_abuse_limits_still_fire_and_escalate_under_overload(self):
        for _ in range(3):
            self.round(errors=3)
        self.assertEqual(smart.LAST["action"], "shed")
        # 20 a minute per member, 6 went before in these rounds: the per-member limit fires for P0 as for any tier.
        statuses = [self.client.post("/p0/", **self.bearer).status_code for _ in range(30)]
        self.assertEqual(statuses[:14], [200] * 14)
        self.assertEqual(set(statuses[14:]), {429})
        self.clock.advance(16)  # a new minute window, but ten refusals blocked the caller for 30 s
        blocked = self.client.post("/p0/", **self.bearer)
        self.assertEqual((blocked.status_code, blocked.json()["retry_after"]), (429, 14))
        other = Member.objects.create_user(email="p0-other@example.com", password="pw-123456!", is_active=True)
        fresh = {"HTTP_AUTHORIZATION": f"Bearer {RefreshToken.for_user(other).access_token}"}
        self.assertEqual(self.client.post("/p0/", **fresh).status_code, 200)


@limiter_on(admission={"concurrency_limit": 20, "p0_reserved_slots": 2})
class AdmissionTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        self.client = APIClient()

    def statuses_with_in_flight(self, busy: int):
        signals.INFLIGHT.count = busy
        result = {path: self.client.get(f"/{path}/").status_code for path in ("p0", "p1", "p2", "p3")}
        self.assertEqual(signals.in_flight(), busy)  # every admitted request gave its slot back
        return result

    def test_lower_tiers_stop_at_their_share_and_p0_keeps_the_reserved_slots(self):
        self.assertEqual(self.statuses_with_in_flight(9), {"p0": 200, "p1": 200, "p2": 200, "p3": 200})
        self.assertEqual(self.statuses_with_in_flight(10), {"p0": 200, "p1": 200, "p2": 200, "p3": 429})
        self.assertEqual(self.statuses_with_in_flight(14), {"p0": 200, "p1": 200, "p2": 429, "p3": 429})
        self.assertEqual(self.statuses_with_in_flight(18), {"p0": 200, "p1": 429, "p2": 429, "p3": 429})
        self.assertEqual(self.statuses_with_in_flight(19)["p0"], 200)

    def test_a_refusal_for_lack_of_a_slot_is_short_and_counts_as_overload(self):
        signals.INFLIGHT.count = 12
        response = self.client.get("/p3/")
        self.assertEqual((response.status_code, response["Retry-After"]), (429, "2"))
        self.assertEqual(signals.WINDOW.refused, 1)
        self.assertEqual(signals.WINDOW.scopes["t-p3"].limited, 1)

    def test_a_fixed_p2_scope_is_never_shed_but_still_takes_p2_slots(self):
        signals.INFLIGHT.count = 14
        self.assertEqual(self.client.get("/fixed/").status_code, 429)
        registry.configs(0)
        self.assertFalse(registry.REGISTRY.configs["t-fixed"].sheddable)
