"""What bounds ``POST /analytics/pageview/`` now that the client IP does not: cache placement, total cap, field sizes.

The per-visitor throttle is keyed on a value the client chooses, so a script can mint a fresh key per request:

- every key is a cache entry. Throttle history therefore lives in the bounded in-process ``throttle`` alias and never
  in the default cache (in production a per-container file cache, where each key is a file and every write lists
  the directory);
- every accepted page view is a row. One constant-key bucket caps all page views of a process at 3,000 a minute,
  far above the campus peak (about 150);
- every row stores request metadata. Each stored field is cut or rejected at its column size.
"""

import logging
import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.cache import cache, caches
from django.test import SimpleTestCase, override_settings

from apps.cms.models import PageView
from apps.cms.services.analytics import (
    PATH_MAX_BYTES,
    PATH_MAX_LENGTH,
    REFERRER_MAX_LENGTH,
    SESSION_KEY_MAX_LENGTH,
    USER_AGENT_MAX_LENGTH,
    VISITOR_ID_MAX_LENGTH,
    bounded_page_view,
    enqueue,
    flush_sync,
)
from apps.cms.services.analytics.record import clean_ip_address, clean_session_key
from apps.cms.views.analytics import (
    PageViewCreateView,
    PageViewLegacyThrottle,
    PageViewTotalThrottle,
    PageViewVisitorThrottle,
)
from apps.core.utils.throttle_cache import throttle_cache
from config.settings.components.framework.cache import THROTTLE_CACHE

from .test_pageview_visitor import CAMPUS_IP, LEGACY_RATE, URL, VISITOR_RATE, PageViewVisitorTestCase

TOTAL_RATE = 3000
TOTAL_KEY = "throttle_pageview_total_all"
LEGACY_KEY = "throttle_pageview_legacy_legacy"
WARNED_KEY = "pageview_total_cap_warned"
VIEW_LOGGER = "apps.cms.views.analytics"
THROTTLED_DETAIL = "Request was throttled. Expected available in 60 seconds."


def visitor_key(visitor_id: str) -> str:
    return f"throttle_pageview_visitor_visitor:{visitor_id}"


def stored_keys(alias: str) -> set[str]:
    """Every key a LocMemCache alias holds, as the caller wrote it (without the ``prefix:version:`` part)."""
    return {key.split(":", 2)[2] for key in caches[alias]._cache}


def total_count() -> int:
    """How many page views the total bucket has counted in the current window."""
    return len(throttle_cache.get(TOTAL_KEY, []))


class ThrottleCachePlacementTests(PageViewVisitorTestCase):
    def test_all_three_throttles_keep_their_history_in_the_throttle_alias(self):
        for throttle in (PageViewVisitorThrottle, PageViewLegacyThrottle, PageViewTotalThrottle):
            with self.subTest(throttle=throttle.__name__):
                self.assertIs(throttle.cache, throttle_cache)
                self.assertIs(throttle().cache, throttle_cache)

    def test_page_views_never_write_to_the_default_cache(self):
        visitor = str(uuid.uuid4())

        statuses = [self.view(visitor) for _ in range(VISITOR_RATE + 1)]
        legacy_status = self.view()

        self.assertEqual(statuses, [201] * VISITOR_RATE + [429])
        self.assertEqual(legacy_status, 201)
        self.assertEqual(stored_keys("default"), set())
        self.assertEqual(stored_keys("throttle"), {visitor_key(visitor), LEGACY_KEY, TOTAL_KEY})
        self.assertEqual(len(throttle_cache.get(visitor_key(visitor))), VISITOR_RATE)
        self.assertEqual(len(throttle_cache.get(LEGACY_KEY)), 1)

    def test_page_views_are_throttled_while_the_default_cache_refuses_every_call(self):
        refuse = Mock(side_effect=AssertionError("a page view touched the default cache"))
        visitor = str(uuid.uuid4())

        with patch.multiple(caches["default"], get=refuse, set=refuse, add=refuse, incr=refuse, touch=refuse):
            statuses = [self.view(visitor) for _ in range(VISITOR_RATE + 1)]
            legacy_status = self.view()

        refuse.assert_not_called()
        self.assertEqual(statuses, [201] * VISITOR_RATE + [429])
        self.assertEqual(legacy_status, 201)

    def test_minted_ids_leave_no_file_in_a_production_style_file_cache(self):
        """The production default cache without Redis: one file per key, the directory listed on every write."""
        with tempfile.TemporaryDirectory() as directory:
            production_like = {
                "default": {
                    "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                    "LOCATION": directory,
                    "KEY_PREFIX": "i2g",
                    "OPTIONS": {"MAX_ENTRIES": 2_000},
                },
                "throttle": {**THROTTLE_CACHE, "LOCATION": "pageview-file-cache-probe"},
            }
            with override_settings(CACHES=production_like):
                self.addCleanup(caches["throttle"].clear)

                statuses = [self.view(str(uuid.uuid4())) for _ in range(300)]
                statuses.append(self.view())

                self.assertEqual(statuses, [201] * 301)
                self.assertEqual(list(Path(directory).iterdir()), [])
                # 300 visitor buckets, the legacy bucket and the total bucket.
                self.assertEqual(len(caches["throttle"]._cache), 302)
                caches["throttle"].clear()

    def test_a_flood_of_minted_ids_cannot_grow_the_throttle_cache_past_its_cap(self):
        small = {**THROTTLE_CACHE, "LOCATION": "pageview-bound-probe", "OPTIONS": {"MAX_ENTRIES": 50}}
        with override_settings(CACHES={**settings.CACHES, "throttle": small}):
            self.addCleanup(caches["throttle"].clear)
            sizes = []
            for _ in range(400):
                self.assertEqual(self.view(str(uuid.uuid4())), 201)
                sizes.append(len(caches["throttle"]._cache))

            # 400 minted ids, never more than 50 entries: each cull drops the least recently used third.
            self.assertLessEqual(max(sizes), 50)
            self.assertGreater(max(sizes), 40)
            self.assertLess(min(sizes[100:]), max(sizes))
            # The bucket every request reads is never the least recently used entry, so the culls spare it.
            self.assertEqual(total_count(), 400)
            self.assertEqual(stored_keys("default"), set())
            caches["throttle"].clear()


class TotalCapTests(PageViewVisitorTestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        super().setUp()
        # Reaching the cap logs an operator warning; keep it out of the test output (assertLogs still sees it).
        view_logger = logging.getLogger(VIEW_LOGGER)
        handler = logging.NullHandler()
        view_logger.addHandler(handler)
        self.addCleanup(view_logger.removeHandler, handler)
        propagate = patch.object(view_logger, "propagate", False)
        propagate.start()
        self.addCleanup(propagate.stop)

    def response(self, visitor_id=None):
        payload = {"path": "/"} if visitor_id is None else {"path": "/", "visitor_id": visitor_id}
        return self.client.post(URL, payload, format="json", REMOTE_ADDR=CAMPUS_IP, HTTP_X_FORWARDED_FOR=CAMPUS_IP)

    def test_the_cap_is_three_thousand_a_minute_under_one_constant_key(self):
        throttle = PageViewTotalThrottle()

        self.assertEqual(PageViewTotalThrottle.rate, "3000/min")
        self.assertEqual((throttle.num_requests, throttle.duration), (TOTAL_RATE, 60))
        self.assertEqual(throttle.get_cache_key(None, None), TOTAL_KEY)
        # Checked around the per-visitor / legacy throttles, not as one of them (see check_throttles).
        self.assertEqual(PageViewCreateView.throttle_classes, [PageViewVisitorThrottle, PageViewLegacyThrottle])

    def test_three_thousand_visitors_in_a_minute_are_stored_and_the_next_page_view_is_refused(self):
        visitors = [str(uuid.uuid4()) for _ in range(TOTAL_RATE)]

        statuses = [self.view(visitor) for visitor in visitors]

        self.assertEqual(statuses.count(201), TOTAL_RATE)
        self.assertEqual(len(statuses), TOTAL_RATE)
        # The 3001st page view of the minute, whoever sends it: a new visitor, an old bundle, a known visitor.
        self.assertEqual(self.view(str(uuid.uuid4())), 429)
        self.assertEqual(self.view(), 429)
        self.assertEqual(self.view(visitors[0]), 429)
        flush_sync()
        self.assertEqual(PageView.objects.count(), TOTAL_RATE)
        self.assertEqual(set(PageView.objects.values_list("visitor_id", flat=True)), set(visitors))
        self.assertEqual(stored_keys("default"), set())

    def test_the_cap_frees_up_a_minute_later(self):
        for _ in range(TOTAL_RATE):
            self.view(str(uuid.uuid4()))
        self.assertEqual(self.view(str(uuid.uuid4())), 429)

        self.clock.now += 59
        self.assertEqual(self.view(str(uuid.uuid4())), 429)
        self.clock.now += 1

        self.assertEqual(self.view(str(uuid.uuid4())), 201)
        self.assertEqual(total_count(), 1)

    def test_the_refusal_is_the_same_429_the_per_visitor_rate_answers(self):
        noisy = str(uuid.uuid4())
        for _ in range(VISITOR_RATE):
            self.response(noisy)
        per_visitor = self.response(noisy)
        self.assertEqual(total_count(), VISITOR_RATE)

        with patch.object(PageViewTotalThrottle, "rate", f"{VISITOR_RATE}/min"):
            over_the_cap = self.response(str(uuid.uuid4()))

        for response in (per_visitor, over_the_cap):
            self.assertEqual(response.status_code, 429)
            self.assertEqual(str(response.data["detail"]), THROTTLED_DETAIL)
            self.assertEqual(response.data["detail"].code, "throttled")
            self.assertEqual(response["Retry-After"], "60")
        self.assertEqual(over_the_cap.data, per_visitor.data)

    def test_page_views_refused_by_the_per_visitor_rate_do_not_use_up_the_total(self):
        """One runaway browser costs 120 of the 3,000, however fast it loops."""
        runaway = str(uuid.uuid4())

        statuses = [self.view(runaway) for _ in range(500)]

        self.assertEqual(statuses, [201] * VISITOR_RATE + [429] * (500 - VISITOR_RATE))
        self.assertEqual(total_count(), VISITOR_RATE)

    def test_page_views_refused_by_the_legacy_rate_do_not_use_up_the_total(self):
        statuses = [self.view() for _ in range(LEGACY_RATE + 50)]

        self.assertEqual(statuses, [201] * LEGACY_RATE + [429] * 50)
        self.assertEqual(total_count(), LEGACY_RATE)

    def test_over_the_cap_nothing_is_counted_and_a_minted_id_gets_no_bucket(self):
        with patch.object(PageViewTotalThrottle, "rate", "5/min"):
            self.assertEqual([self.view(str(uuid.uuid4())) for _ in range(5)], [201] * 5)
            keys_at_the_cap = stored_keys("throttle")
            minted = [str(uuid.uuid4()) for _ in range(20)]

            self.assertEqual([self.view(visitor) for visitor in minted], [429] * 20)
            self.assertEqual(self.view(), 429)

            # Nothing new but the once-a-minute marker of the operator warning.
            self.assertEqual(stored_keys("throttle"), keys_at_the_cap | {WARNED_KEY})
            self.assertEqual(total_count(), 5)
        flush_sync()
        self.assertEqual(PageView.objects.count(), 5)

    def test_reaching_the_cap_is_logged_once_a_minute_for_operators(self):
        with patch.object(PageViewTotalThrottle, "rate", "3/min"):
            with self.assertLogs(VIEW_LOGGER, level="WARNING") as logs:
                statuses = [self.view(str(uuid.uuid4())) for _ in range(30)]

            self.assertEqual(statuses, [201] * 3 + [429] * 27)
            self.assertEqual(len(logs.records), 1)
            message = logs.records[0].getMessage()
            self.assertTrue(message.startswith("analytics.pageview_total_cap limit=3 window_seconds=60"), message)
            # No visitor id, path or address in the line.
            self.assertNotIn(CAMPUS_IP, message)

            # A minute later the marker has expired: the next refusal is reported again.
            throttle_cache.delete(WARNED_KEY)
            with self.assertLogs(VIEW_LOGGER, level="WARNING") as logs:
                self.assertEqual(self.view(str(uuid.uuid4())), 429)
            self.assertEqual(len(logs.records), 1)

    def test_nothing_is_logged_below_the_cap(self):
        noisy = str(uuid.uuid4())

        with self.assertNoLogs(VIEW_LOGGER, level="WARNING"):
            statuses = [self.view(noisy) for _ in range(VISITOR_RATE + 5)]
            self.view()

        self.assertEqual(statuses.count(429), 5)
        self.assertNotIn(WARNED_KEY, stored_keys("throttle"))

    def test_honest_visitors_below_the_cap_keep_their_own_rate(self):
        visitors = [str(uuid.uuid4()) for _ in range(20)]

        for visitor in visitors:
            self.assertEqual([self.view(visitor) for _ in range(VISITOR_RATE)], [201] * VISITOR_RATE)

        # 2,400 page views so far: under the cap, so each visitor meets only their own 120 a minute.
        self.assertEqual([self.view(visitor) for visitor in visitors], [429] * 20)
        self.assertEqual(self.view(str(uuid.uuid4())), 201)
        self.assertEqual(self.view(), 201)
        self.assertEqual(total_count(), 20 * VISITOR_RATE + 2)
        flush_sync()
        self.assertEqual(PageView.objects.count(), 20 * VISITOR_RATE + 2)

    def test_the_client_ip_is_no_part_of_the_cap(self):
        with patch.object(PageViewTotalThrottle, "rate", "3/min"):
            for index in range(3):
                address = f"203.0.113.{index + 1}"
                response = self.client.post(
                    URL,
                    {"path": "/", "visitor_id": str(uuid.uuid4())},
                    format="json",
                    REMOTE_ADDR=address,
                    HTTP_X_FORWARDED_FOR=address,
                )
                self.assertEqual(response.status_code, 201)

            response = self.client.post(
                URL,
                {"path": "/", "visitor_id": str(uuid.uuid4())},
                format="json",
                REMOTE_ADDR="198.51.100.7",
                HTTP_X_FORWARDED_FOR="198.51.100.7",
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(stored_keys("throttle") & {TOTAL_KEY}, {TOTAL_KEY})
        self.assertFalse([key for key in stored_keys("throttle") if "203.0.113" in key or "198.51.100" in key])


class StoredFieldBoundTests(PageViewVisitorTestCase):
    def post(self, body=None, **extra):
        return self.client.post(URL, {"path": "/", **(body or {})}, format="json", **extra)

    def test_the_limits_are_the_column_sizes(self):
        def column(name):
            return PageView._meta.get_field(name).max_length

        self.assertEqual(PATH_MAX_LENGTH, column("path"))
        self.assertEqual(REFERRER_MAX_LENGTH, column("referrer"))
        self.assertEqual(SESSION_KEY_MAX_LENGTH, column("session_key"))
        self.assertEqual(VISITOR_ID_MAX_LENGTH, column("visitor_id"))
        # A TextField: no column limit, so the write path is the only bound.
        self.assertIsNone(column("user_agent"))
        self.assertEqual(USER_AGENT_MAX_LENGTH, 512)
        # The path is indexed; PostgreSQL refuses a B-tree entry over about 2,700 bytes.
        self.assertEqual(PATH_MAX_BYTES, 2048)
        self.assertTrue(PageView._meta.get_field("path").db_index)

    def test_a_non_ascii_path_is_cut_to_the_byte_budget_of_its_index(self):
        """2,048 characters pass the serializer, but as UTF-8 they can be 8 kB: more than an index entry holds."""
        for index, (character, kept) in enumerate((("é", 1023), ("中", 682), ("😀", 511))):
            with self.subTest(character=character):
                marker = str(index)
                self.assertEqual(self.post({"path": marker + character * (PATH_MAX_LENGTH - 1)}).status_code, 201)

                flush_sync()

                stored = PageView.objects.get(path__startswith=marker).path
                self.assertEqual(stored, marker + character * kept)
                self.assertLessEqual(len(stored.encode()), PATH_MAX_BYTES)
                self.assertGreater(len((stored + character).encode()), PATH_MAX_BYTES)

    def test_a_long_user_agent_is_cut_to_512_characters(self):
        agent = "Mozilla/5.0 " + "x" * 4000

        self.assertEqual(self.post(HTTP_USER_AGENT=agent).status_code, 201)

        flush_sync()
        self.assertEqual(PageView.objects.get().user_agent, agent[:512])

    def test_a_user_agent_of_exactly_512_characters_is_stored_whole(self):
        agent = "a" * 512

        self.assertEqual(self.post(HTTP_USER_AGENT=agent).status_code, 201)

        flush_sync()
        self.assertEqual(PageView.objects.get().user_agent, agent)

    def test_a_path_of_the_column_size_is_stored_and_one_character_more_is_rejected(self):
        longest = "/" + "p" * (PATH_MAX_LENGTH - 1)

        self.assertEqual(self.post({"path": longest}).status_code, 201)
        rejected = self.post({"path": longest + "p"})

        self.assertEqual(rejected.status_code, 400)
        self.assertIn("path", rejected.data)
        flush_sync()
        self.assertEqual([page_view.path for page_view in PageView.objects.all()], [longest])

    def test_a_referrer_of_the_column_size_is_stored_and_one_character_more_is_rejected(self):
        longest = "https://example.com/" + "r" * (REFERRER_MAX_LENGTH - len("https://example.com/"))

        self.assertEqual(self.post({"referrer": longest}).status_code, 201)
        rejected = self.post({"referrer": longest + "r"})

        self.assertEqual(rejected.status_code, 400)
        self.assertIn("referrer", rejected.data)
        flush_sync()
        self.assertEqual([page_view.referrer for page_view in PageView.objects.all()], [longest])

    def test_a_session_cookie_that_cannot_be_a_session_key_is_not_stored(self):
        self.client.cookies[settings.SESSION_COOKIE_NAME] = "s" * 200
        self.assertEqual(self.post({"path": "/junk-cookie"}).status_code, 201)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = "k" * 32
        self.assertEqual(self.post({"path": "/session"}).status_code, 201)

        flush_sync()
        self.assertEqual(PageView.objects.get(path="/junk-cookie").session_key, "")
        self.assertEqual(PageView.objects.get(path="/session").session_key, "k" * 32)

    def test_a_forged_client_address_is_stored_as_null_and_never_loses_the_batch(self):
        """Without trusted-proxy settings the address is the first X-Forwarded-For entry: any text the client likes.

        A batch is one ``bulk_create``; a value the field or the database refuses would drop every row in it.
        """
        forged = ["not-an-ip", "a:b", "1.2.3.4.5", "999.1.1.1", "fe80::1%eth0", "x" * 500, "'; DROP TABLE--"]
        for index, value in enumerate(forged):
            self.assertEqual(self.post({"path": f"/forged-{index}"}, HTTP_X_FORWARDED_FOR=value).status_code, 201)
        self.assertEqual(self.post({"path": "/honest"}, HTTP_X_FORWARDED_FOR=CAMPUS_IP).status_code, 201)
        self.assertEqual(self.post({"path": "/v6"}, HTTP_X_FORWARDED_FOR="2001:0db8:0000::0001").status_code, 201)

        flush_sync()

        self.assertEqual(PageView.objects.count(), len(forged) + 2)
        self.assertEqual(
            set(PageView.objects.filter(path__startswith="/forged-").values_list("ip_address", flat=True)), {None}
        )
        self.assertEqual(PageView.objects.get(path="/honest").ip_address, CAMPUS_IP)
        self.assertEqual(PageView.objects.get(path="/v6").ip_address, "2001:db8::1")

    def test_whatever_is_enqueued_directly_is_bounded_too(self):
        enqueue(
            {
                "path": "/" + "p" * 5000,
                "referrer": "https://example.com/" + "r" * 5000,
                "user_agent": "u" * 5000,
                "ip_address": "junk",
                "visitor_id": "v" * 500,
                "session_key": "s" * 500,
                "member": None,
            }
        )

        flush_sync()

        page_view = PageView.objects.get()
        self.assertEqual(len(page_view.path), PATH_MAX_LENGTH)
        self.assertEqual(len(page_view.referrer), REFERRER_MAX_LENGTH)
        self.assertEqual(page_view.user_agent, "u" * USER_AGENT_MAX_LENGTH)
        self.assertEqual((page_view.ip_address, page_view.visitor_id, page_view.session_key), (None, None, ""))


class BoundedPageViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_text_is_cut_at_its_limit_and_loses_nul_characters(self):
        bounded = bounded_page_view(
            {"path": "/a\x00b" + "p" * 3000, "referrer": "r" * 3000, "user_agent": "Mozilla\x00/5.0 " + "u" * 600}
        )

        self.assertEqual(bounded["path"], ("/ab" + "p" * 3000)[:PATH_MAX_LENGTH])
        self.assertEqual(bounded["referrer"], "r" * REFERRER_MAX_LENGTH)
        self.assertEqual(bounded["user_agent"], ("Mozilla/5.0 " + "u" * 600)[:USER_AGENT_MAX_LENGTH])
        self.assertEqual(len(bounded["user_agent"]), 512)

    def test_lone_surrogates_are_removed(self):
        """No database encoding can store one; left in, the whole batch would fail to encode."""
        bounded = bounded_page_view(
            {"path": "/a\ud800b", "referrer": "https://example.com/\udfff", "user_agent": "Mozilla\ud83d/5.0"}
        )

        self.assertEqual(bounded, {"path": "/ab", "referrer": "https://example.com/", "user_agent": "Mozilla/5.0"})
        for value in bounded.values():
            value.encode("utf-8")

    def test_only_the_indexed_path_is_bounded_in_bytes(self):
        bounded = bounded_page_view({"path": "é" * 3000, "referrer": "é" * 3000, "user_agent": "é" * 3000})

        self.assertEqual(bounded["path"], "é" * (PATH_MAX_BYTES // 2))
        self.assertEqual(bounded["referrer"], "é" * REFERRER_MAX_LENGTH)
        self.assertEqual(bounded["user_agent"], "é" * USER_AGENT_MAX_LENGTH)

    def test_values_within_their_limits_are_unchanged(self):
        member = object()
        data = {
            "path": "/about",
            "referrer": "https://example.com/",
            "user_agent": "Mozilla/5.0",
            "ip_address": "169.236.0.10",
            "visitor_id": "3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f",
            "session_key": "k" * 32,
            "member": member,
        }

        bounded = bounded_page_view(data)

        self.assertEqual(bounded, data)
        self.assertIs(bounded["member"], member)
        self.assertIsNot(bounded, data)

    def test_the_input_is_not_modified_and_absent_fields_stay_absent(self):
        data = {"path": "/", "user_agent": "u" * 600}

        bounded = bounded_page_view(data)

        self.assertEqual(data, {"path": "/", "user_agent": "u" * 600})
        self.assertEqual(bounded, {"path": "/", "user_agent": "u" * 512})

    def test_text_that_is_not_a_string_becomes_empty(self):
        bounded = bounded_page_view({"path": None, "referrer": 7, "user_agent": ["Mozilla"], "session_key": None})

        self.assertEqual(bounded, {"path": "", "referrer": "", "user_agent": "", "session_key": ""})

    def test_a_malformed_visitor_id_becomes_null(self):
        self.assertIsNone(bounded_page_view({"visitor_id": "v" * (VISITOR_ID_MAX_LENGTH + 1)})["visitor_id"])
        self.assertIsNone(bounded_page_view({"visitor_id": "has space"})["visitor_id"])
        self.assertIsNone(bounded_page_view({"visitor_id": None})["visitor_id"])
        self.assertEqual(bounded_page_view({"visitor_id": "v" * VISITOR_ID_MAX_LENGTH})["visitor_id"], "v" * 64)

    def test_session_keys(self):
        self.assertEqual(clean_session_key("k" * 32), "k" * 32)
        self.assertEqual(clean_session_key("k" * SESSION_KEY_MAX_LENGTH), "k" * 64)
        self.assertEqual(clean_session_key("k" * (SESSION_KEY_MAX_LENGTH + 1)), "")
        self.assertEqual(clean_session_key("with\x00nul"), "")
        self.assertEqual(clean_session_key("with\ud800surrogate"), "")
        self.assertEqual(clean_session_key(""), "")
        self.assertEqual(clean_session_key(None), "")
        self.assertEqual(clean_session_key(12345678), "")

    def test_ip_addresses(self):
        for value, expected in (
            ("203.0.113.50", "203.0.113.50"),
            (" 203.0.113.50 ", "203.0.113.50"),
            ("2001:db8::1", "2001:db8::1"),
            ("2001:0DB8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
            ("::1", "::1"),
            ("fe80::1%eth0", None),
            ("203.0.113.50, 10.0.0.1", None),
            ("203.0.113", None),
            ("256.1.1.1", None),
            ("a:b", None),
            ("localhost", None),
            ("", None),
            ("1" * 46, None),
            ("9" * 5000, None),
            (None, None),
            (2130706433, None),
            (b"127.0.0.1", None),
        ):
            with self.subTest(value=value):
                self.assertEqual(clean_ip_address(value), expected)
