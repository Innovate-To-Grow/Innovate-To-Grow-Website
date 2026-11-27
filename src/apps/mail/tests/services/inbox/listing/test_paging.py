"""``reading.paging``: the "Load older" cursor, one position per account."""

from django.test import SimpleTestCase

from apps.mail.services.inbox.reading import paging
from apps.mail.services.inbox.reading.accounts import InboxAccount

IMAP = InboxAccount("imap:7", "imap", "i2g@gmail.com", "imap.gmail.com", 7)
GRAPH = InboxAccount("graph:i2g@contoso.com", "graph", "i2g@contoso.com", "Microsoft Graph")


def rows(*uids):
    return [{"uid": str(uid)} for uid in uids]


class TokenTests(SimpleTestCase):
    def test_a_cursor_survives_the_round_trip(self):
        cursor = {IMAP.key: "u120", GRAPH.key: "s30", "imap:9": "x"}

        token = paging.encode(cursor)

        self.assertRegex(token, r"^[A-Za-z0-9_-]+$")
        self.assertEqual(paging.decode(token), cursor)

    def test_a_malformed_token_starts_every_account_over(self):
        for token in (None, "", "%%%", "bm90IGpzb24", paging.encode([]), "x" * (paging.MAX_TOKEN_LENGTH + 1)):
            with self.subTest(token=token):
                self.assertEqual(paging.decode(token), {})
        too_many = paging.encode({f"imap:{index}": "x" for index in range(paging.MAX_ACCOUNTS + 1)})
        self.assertEqual(paging.decode(too_many), {})

    def test_only_well_formed_positions_are_kept(self):
        token = paging.encode(
            {IMAP.key: "u0", GRAPH.key: "s-1", "a": "u12", "b": "s1234567", "c": "y", "d": 5, "": "x", "e" * 301: "x"}
        )

        self.assertEqual(paging.decode(token), {"a": "u12"})


class PositionTests(SimpleTestCase):
    def test_each_kind_reads_its_own_position(self):
        self.assertEqual(paging.position({IMAP.key: "u120"}, IMAP), paging.Position(before=120))
        self.assertEqual(paging.position({GRAPH.key: "s30"}, GRAPH), paging.Position(skip=30))
        self.assertIsNone(paging.position({IMAP.key: "x"}, IMAP))

    def test_a_missing_or_foreign_position_starts_at_the_newest(self):
        for cursor, account in (({}, IMAP), ({IMAP.key: "s30"}, IMAP), ({GRAPH.key: "u4"}, GRAPH)):
            with self.subTest(cursor=cursor):
                self.assertTrue(paging.position(cursor, account).is_start)

    def test_the_cache_key_part(self):
        self.assertEqual(
            (paging.START.key, paging.Position(before=9).key, paging.Position(skip=30).key), ("", "u9", "s30")
        )


class AdvanceTests(SimpleTestCase):
    def advance(self, account, start, read, shown, *, limit=3, cursor=None):
        cursor = dict(cursor or {})
        paging.advance(cursor, account, start, read, shown, limit)
        return cursor

    def test_imap_continues_below_the_oldest_shown(self):
        read = rows(30, 20, 10)

        self.assertEqual(self.advance(IMAP, paging.START, read, read), {IMAP.key: "u10"})
        self.assertEqual(self.advance(IMAP, paging.START, read, read[:1]), {IMAP.key: "u30"})

    def test_graph_skips_what_it_has_shown(self):
        read = rows("a", "b", "c")

        self.assertEqual(self.advance(GRAPH, paging.Position(skip=30), read, read[:2]), {GRAPH.key: "s32"})

    def test_an_account_whose_whole_short_read_was_shown_is_exhausted(self):
        read = rows(30, 20)

        cursor = self.advance(IMAP, paging.START, read, read)

        self.assertEqual(cursor, {IMAP.key: paging.EXHAUSTED})
        self.assertFalse(paging.has_more(cursor))
        self.assertEqual(self.advance(GRAPH, paging.START, [], []), {GRAPH.key: "x"})

    def test_an_account_none_of_whose_rows_were_kept_starts_at_its_newest_read_again(self):
        read = rows(30, 20, 10)

        self.assertEqual(self.advance(IMAP, paging.START, read, []), {IMAP.key: "u31"})
        self.assertEqual(self.advance(IMAP, paging.Position(before=50), read, [], cursor={IMAP.key: "u50"}),
                         {IMAP.key: "u50"})  # fmt: skip
        self.assertEqual(self.advance(GRAPH, paging.Position(skip=6), read, []), {GRAPH.key: "s6"})

    def test_rows_without_a_numeric_uid_keep_the_position(self):
        self.assertEqual(self.advance(IMAP, paging.START, rows("a", "b", "c"), rows("a")), {})
        self.assertEqual(self.advance(IMAP, paging.START, rows("a", "b", "c"), []), {})

    def test_has_more(self):
        self.assertTrue(paging.has_more({IMAP.key: "x", GRAPH.key: "s3"}))
        self.assertFalse(paging.has_more({}))
