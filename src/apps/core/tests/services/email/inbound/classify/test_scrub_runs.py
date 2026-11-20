"""A run of text without spaces is scrubbed link by link: a personal link loses its token and no more, and the other
links and the person's words around it stay (a CSV row, a pipe-separated line, a sentence, a calendar's "\\n"), in
one pass however many links a line holds. ``scrub_personal_links`` (notes, replies, text files) keeps everything else
as written; ``scrub_links`` (inbound mail) also redacts token-shaped runs, in text and serialized HTML alike."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.services.email.inbound import LINK_PLACEHOLDER as REMOVED
from apps.core.services.email.inbound import scrub_links, scrub_personal_links
from apps.core.services.email.inbound.processing import scrub

TOKEN = "fake-test-token-0000000000"  # synthetic; a real one is secrets.token_urlsafe: [A-Za-z0-9_-]
SIGN_IN = f"https://i2g.ucmerced.edu/login-link#token={TOKEN}"
DOCS = "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit?usp=sharing"
# A one-click token as Django's signing.dumps(..., compress=True) writes it: ".<base64>:<time>:<signature>".
SIGNED = ".eJxNzDEOgCAMBdC7dGZAFIRexpgSGQzVFhaN:1tq2Xy:AbC_dE-fGhIjKlMnOpQrStUvWxYz0123456789ab"
UNSUBSCRIBE = f"https://api.i2g.ucmerced.edu/mail/unsubscribe/{SIGNED}/"
ENCODED = f"https%3A%2F%2Fi2g.ucmerced.edu%2Flogin-link%23token%3D{TOKEN}"
SAFE_LINK = f"https://nam12.safelinks.protection.outlook.com/?url={ENCODED}&data=05%7C02"
# (as written, as scrubbed), each line a case of its own.
LINES = (
    (f"Pat Doe,{DOCS},{SIGN_IN},team A", f"Pat Doe,{DOCS},{REMOVED},team A"),
    (f"Lee Kim,www.example.org/info,{SIGN_IN},team B", f"Lee Kim,www.example.org/info,{REMOVED},team B"),
    (f"Kai,{DOCS},www.i2g.ucmerced.edu/login-link#token={TOKEN},team C", f"Kai,{DOCS},{REMOVED},team C"),
    (f"Jo,https://example.org/a,b,{SIGN_IN};next,team D", f"Jo,https://example.org/a,b,{REMOVED};next,team D"),
    (f"Pat|{SIGN_IN}|team A|R101", f"Pat|{REMOVED}|team A|R101"),
    (f"Did you get {SIGN_IN}?", f"Did you get {REMOVED}?"),
    (f"{SIGN_IN}:", f"{REMOVED}:"),
    (
        f"first: {SIGN_IN}\\nAgenda: posters at 9\\, demos at 10.",
        f"first: {REMOVED}\\nAgenda: posters at 9\\, demos at 10.",
    ),
    (f"(see {SIGN_IN}). It did not work.", f"(see {REMOVED}). It did not work."),
    (f"Sign in at {SIGN_IN}. Then go.", f"Sign in at {REMOVED}. Then go."),
    (f"Stop: {UNSUBSCRIBE}, thanks", f"Stop: {REMOVED}, thanks"),
    (f"(stop: {UNSUBSCRIBE}). Done.", f"(stop: {REMOVED}). Done."),
    (f"(stop: {UNSUBSCRIBE[:-1]}). Done.", f"(stop: {REMOVED}). Done."),
    (f"https://x.example/login-link?next=/a#token={TOKEN},keep", f"{REMOVED},keep"),  # up to the last token
    (f"https://x.example/?token={TOKEN}/unsubscribe/{SIGNED},keep", f"{REMOVED},keep"),  # one in another's value
    (f"Reset: https://www.partner.example/reset?reset_token={TOKEN}.", f"Reset: {REMOVED}."),  # "www." of a host
    (f"{SIGN_IN},{SIGN_IN}", f"{REMOVED},{REMOVED}"),
    (f"请点击{SIGN_IN}，谢谢", f"请点击{REMOVED}，谢谢"),  # glued to a word: still a link
    (f"first:\\nwww.i2g.ucmerced.edu/login-link#token={TOKEN}\\nAgenda", f"first:\\n{REMOVED}\\nAgenda"),
    (f"Open {SAFE_LINK} now.", f"Open {REMOVED} now."),  # personal only inside: the wrapper goes whole
    (f"https://i2g.ucmerced.edu/login-link?next={ENCODED},keep", REMOVED),  # one encoded past the visible one
)


class PersonalLinkTests(SimpleTestCase):
    def test_each_link_of_a_run_is_judged_on_its_own_and_only_its_token_goes(self):
        for line, scrubbed in LINES:
            with self.subTest(line):
                self.assertEqual(scrub_personal_links(line), scrubbed)

    def test_other_links_and_the_words_after_a_link_are_kept_as_written(self):
        # Staff's own text: a token-shaped run, in a link or after one, is no personal link and stays.
        opaque = "https://files.example/get?id=" + "Q" * 70 + "&x=1"
        line = f"Ref {'R' * 70}, see {opaque},{SIGN_IN},{'A' * 70} (end)"

        self.assertEqual(scrub_personal_links(line), f"Ref {'R' * 70}, see {opaque},{REMOVED},{'A' * 70} (end)")
        self.assertEqual(scrub_personal_links(None), "")


class ScrubLinksTests(SimpleTestCase):
    def test_the_same_words_stay_in_text_and_in_serialized_html(self):
        for line, scrubbed in LINES:
            with self.subTest(line):
                self.assertEqual(scrub_links(line), scrubbed)
                self.assertEqual(
                    scrub_links(f'<p><a href="{SIGN_IN}">{line}</a></p>'), f'<p><a href="{REMOVED}">{scrubbed}</a></p>'
                )

    def test_token_shaped_runs_go_in_links_and_after_a_personal_one(self):
        opaque = "https://files.example/get?id=" + "Q" * 70 + "&x=1"
        line = f"Ref {'R' * 70}, see {opaque},{SIGN_IN},{'A' * 70} (end)"

        self.assertEqual(
            scrub_links(line),
            f"Ref [redacted], see https://files.example/get?id=[redacted]&x=1,{REMOVED},[redacted] (end)",
        )


class LongLineTests(SimpleTestCase):
    def test_thousands_of_links_on_one_line_are_read_in_one_pass(self):
        # The helpdesk's old rule called itself once per link (RecursionError past about 1,000) and judged the rest
        # of the line again each time.
        signs = ",".join([SIGN_IN] * 2000)
        docs = ",".join([DOCS] * 2000) + f",{SIGN_IN}"
        for scrubbed in (scrub_personal_links, scrub_links):
            with (
                self.subTest(scrubbed.__name__),
                patch.object(scrub, "is_sensitive_url", wraps=scrub.is_sensitive_url) as judged,
            ):
                self.assertEqual(scrubbed(signs), ",".join([REMOVED] * 2000))
                self.assertEqual(scrubbed(docs), ",".join([DOCS] * 2000) + f",{REMOVED}")
                read = sum(len(call.args[0]) for call in judged.call_args_list)
                self.assertLess(read, 2 * (len(signs) + len(docs)))  # each character judged about once: linear
