"""Recent 429 counts for the admin: what the limiter, the view's own limits and the 404 limiter count, the history
window, and the counter store's fail-open helpers they use."""

import copy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.services.request_limits.runtime import refusals, store

from .helpers import START, TEST_SCOPES, isolate, limiter_on, limits_with

Member = get_user_model()


@limiter_on()
class LimiterCountsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = isolate(self)
        self.client = APIClient()
        member = Member.objects.create_user(email="refusals@example.com", password="pw-123456!", is_active=True)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}")

    def test_the_limiter_and_the_view_refusals_are_counted_apart(self):
        statuses = [self.client.get("/p0/").status_code for _ in range(7)]
        self.assertEqual(statuses, [200] * 5 + [429] * 2)
        self.clock.advance(60)
        self.assertEqual(self.client.get("/p0-refused/").status_code, 429)

        recent = refusals.recent(["t-p0", "t-p1"], self.clock())

        self.assertEqual(recent, {"t-p0": {"limiter": 2, "view": 1}, "t-p1": {"limiter": 0, "view": 0}})

    def test_unmatched_paths_count_in_the_not_found_scope(self):
        scopes = {**copy.deepcopy(TEST_SCOPES), "not-found": {**TEST_SCOPES["t-p3"], "requests": 1}}
        with override_settings(REQUEST_RATE_LIMITS=limits_with(scopes=scopes)):
            self.client.credentials()
            statuses = [self.client.get("/missing/").status_code for _ in range(3)]

            recent = refusals.recent(["not-found"], self.clock())

        self.assertEqual(statuses, [404, 429, 429])
        self.assertEqual(recent["not-found"], {"limiter": 2, "view": 0})


class HistoryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = isolate(self)

    def test_the_last_minutes_are_summed_and_older_ones_dropped(self):
        refusals.count("ai", START, by_limiter=True)
        refusals.count("ai", START + 30, by_limiter=False)
        refusals.count("ai", START + 14 * 60, by_limiter=True)

        self.assertEqual(refusals.recent(["ai"], START + 14 * 60), {"ai": {"limiter": 2, "view": 1}})
        # 15 minutes after the first minute began, it is out of the window.
        self.assertEqual(refusals.recent(["ai"], START + 15 * 60), {"ai": {"limiter": 1, "view": 0}})
        self.assertEqual(refusals.recent(["ai"], START + 28 * 60), {"ai": {"limiter": 1, "view": 0}})
        self.assertEqual(refusals.recent(["ai"], START + 29 * 60), {"ai": {"limiter": 0, "view": 0}})

    def test_the_window_follows_the_setting(self):
        config = copy.deepcopy(limits_with(scopes={}))
        config["store"]["refusal_history_minutes"] = 2
        with override_settings(REQUEST_RATE_LIMITS=config):
            refusals.count("ai", START, by_limiter=True)
            self.assertEqual(refusals.history_minutes(), 2)
            self.assertEqual(refusals.recent(["ai"], START + 60)["ai"]["limiter"], 1)
            self.assertEqual(refusals.recent(["ai"], START + 120)["ai"]["limiter"], 0)

    def test_the_buckets_live_as_long_as_the_window(self):
        with patch.object(store, "hit") as hit:
            refusals.count("ai", START, by_limiter=False)
        hit.assert_called_once_with("refused|view|ai", 60, START, keep=16 * 60)

    def test_foreign_values_in_the_buckets_are_ignored(self):
        name = store.window_key("refused|limiter|ai", 60, START)
        store.put(name, "x", 60)
        self.assertEqual(refusals.recent(["ai"], START), {"ai": {"limiter": 0, "view": 0}})
        store.put(name, True, 60)
        self.assertEqual(refusals.recent(["ai"], START), {"ai": {"limiter": 0, "view": 0}})

    def test_no_scopes_read_nothing(self):
        self.assertEqual(refusals.recent([], START), {})


class StoreHelperTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_hit_keeps_the_counter_as_long_as_asked(self):
        with patch.object(store, "_cache") as backend:
            backend.return_value.incr.return_value = 1
            store.hit("b", 60, START, keep=900)
            store.hit("b", 60, START)
        timeouts = [call.kwargs["timeout"] for call in backend.return_value.add.call_args_list]
        self.assertEqual(timeouts, [900, 61])

    def test_hit_reopens_an_expired_counter_with_the_same_lifetime(self):
        with patch.object(store, "_cache") as backend:
            backend.return_value.incr.side_effect = ValueError
            self.assertEqual(store.hit("b", 60, START, keep=900), 1)
        backend.return_value.set.assert_called_once()
        self.assertEqual(backend.return_value.set.call_args.kwargs["timeout"], 900)

    def test_get_many_fails_open(self):
        with patch.object(store, "_cache") as backend:
            backend.return_value.get_many.side_effect = RuntimeError("down")
            with self.assertLogs("apps.core.services.request_limits.runtime.store", "WARNING"):
                self.assertEqual(store.get_many(["a"]), {})

    def test_get_many_reads_the_values(self):
        store.put("rl:a", 3, 60)
        self.assertEqual(store.get_many(["rl:a", "rl:b"]), {"rl:a": 3})
