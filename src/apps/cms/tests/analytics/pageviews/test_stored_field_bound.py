from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore

from apps.cms.models import PageView
from apps.cms.services.analytics import (
    PATH_MAX_BYTES,
    PATH_MAX_LENGTH,
    REFERRER_MAX_LENGTH,
    SESSION_KEY_MAX_LENGTH,
    USER_AGENT_MAX_LENGTH,
    VISITOR_ID_MAX_LENGTH,
    enqueue,
    flush_sync,
)

from .test_pageview_visitor import CAMPUS_IP, URL, PageViewVisitorTestCase


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
        # A real session: with the request limiter on, resolving the caller loads the session, so a cookie naming
        # no stored session no longer reads as a session key.
        session = SessionStore()
        session.create()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
        self.assertEqual(self.post({"path": "/session"}).status_code, 201)

        flush_sync()
        self.assertEqual(PageView.objects.get(path="/junk-cookie").session_key, "")
        self.assertEqual(PageView.objects.get(path="/session").session_key, session.session_key)

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
