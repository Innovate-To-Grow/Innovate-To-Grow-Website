"""Personal links in shapes the scrubber once missed: the site's SMS short link (``/l/<token>``, personal only on the
site's own hosts, so Teams' ``/l/meetup-join/…`` stays), a link JSON-escaped (``https:\\/\\/…``), and a link wrapped
by Proofpoint URL Defense (v2's "-XX" and "_", v3's "*" marks), which goes whole like a Safe Links wrapper."""

from django.test import SimpleTestCase, override_settings

from apps.core.services.email.inbound import LINK_PLACEHOLDER as REMOVED
from apps.core.services.email.inbound import is_sensitive_url, scrub_links, scrub_personal_links, scrub_subject

from .test_scrub_runs import DOCS, SIGN_IN, TOKEN, UNSUBSCRIBE

SMS = "https://i2g.ucmerced.edu/l/SmSsHoRt7kQ2pRt4sQ9pXw"  # FRONTEND_URL + "/l/" + secrets.token_urlsafe(16)
TEAMS = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_NjQ5ZDY4YTktYzQ1%40thread.v2/0?context=%7b%7d"
PROOFPOINT_V2 = (
    "https://urldefense.proofpoint.com/v2/url?u=https-3A__i2g.ucmerced.edu_login-2Dlink-23token-3D"
    f"{TOKEN.replace('-', '-2D')}&d=DwMFaQ&c=AbCd&r=EfGh&m=IjKl&s=MnOp&e="
)
PROOFPOINT_V3 = f"https://urldefense.com/v3/__{SIGN_IN.replace('#', '*')}__;Iw!!AbCdEf!ghIjKl$"  # "Iw": "#"


def json_escaped(value: str) -> str:
    """``value`` as a JSON writer that escapes "/" (PHP's ``json_encode``) writes it."""
    return value.replace("/", "\\/")


@override_settings(FRONTEND_URL="https://I2G.ucmerced.edu", BACKEND_URL="https://api.i2g.ucmerced.edu/")
class SiteShortLinkTests(SimpleTestCase):
    def test_the_sms_link_on_the_sites_own_hosts_goes_up_to_the_end_of_its_token(self):
        line = f"Got: {SMS} is it yours? ({SMS.replace('i2g.', 'I2G.')}). {SMS}/,next"

        for scrubbed in (scrub_personal_links, scrub_links):
            with self.subTest(scrubbed.__name__):
                self.assertEqual(scrubbed(line), f"Got: {REMOVED} is it yours? ({REMOVED}). {REMOVED}/,next")
        self.assertTrue(is_sensitive_url(SMS.replace("i2g.", "api.i2g.")))  # BACKEND_URL's host too
        self.assertEqual(scrub_subject(f"Fwd: my link {SMS}"), f"Fwd: my link {REMOVED}")
        self.assertEqual(scrub_personal_links(json_escaped(f'"{SMS}"')), f'"{REMOVED}"')

    def test_l_links_of_other_hosts_stay(self):
        line = f"Join {TEAMS}, https://example.org/l/SmSsHoRt7kQ2pRt4sQ9pXw or https://i2g.ucmerced.edu/l/short-one"

        self.assertEqual(scrub_personal_links(line), line)
        self.assertEqual(scrub_links(line), line)
        self.assertFalse(is_sensitive_url(SMS.replace("i2g.", "evil-i2g.")))
        with override_settings(FRONTEND_URL="", BACKEND_URL=None):  # no host set: no link is the site's
            self.assertEqual(scrub_personal_links(SMS), SMS)


class WrappedLinkTests(SimpleTestCase):
    def test_a_json_escaped_link_is_found_and_its_token_goes(self):
        # A token holding an escaped "/" goes whole; an ordinary link stays as written.
        links = (SIGN_IN, SIGN_IN.replace("://", "://www."), UNSUBSCRIBE, "https://partner.example/?reset_token=ab/c+d")
        line = ", ".join(f'"{json_escaped(link)}"' for link in (*links, DOCS))

        for scrubbed in (scrub_personal_links, scrub_links):
            with self.subTest(scrubbed.__name__):
                self.assertEqual(scrubbed(line), ", ".join([f'"{REMOVED}"'] * len(links) + [f'"{json_escaped(DOCS)}"']))

    def test_a_link_wrapped_by_proofpoint_goes_whole(self):
        line = f"Gateway: {PROOFPOINT_V2} and {PROOFPOINT_V3} done"

        for scrubbed in (scrub_personal_links, scrub_links):
            with self.subTest(scrubbed.__name__):
                self.assertEqual(scrubbed(line), f"Gateway: {REMOVED} and {REMOVED} done")
        # The characters v3 replaced are read back from its list ("Ojo": "::"), not guessed.
        colons = (
            "https://urldefense.com/v3/__https://api.i2g.ucmerced.edu/mail/unsubscribe/eJx*1tq2Xy*AbC_dE/__;Ojo!!a$"
        )
        self.assertTrue(is_sensitive_url(colons))

    def test_a_proofpoint_wrapper_of_an_ordinary_link_stays(self):
        for link in (
            f"https://urldefense.com/v3/__{DOCS}*tab=t.0__;Iw!!AbCdEf!ghIjKl$",
            "https://urldefense.proofpoint.com/v2/url?u=https-3A__docs.google.com_document_d_1AbC_edit&d=DwMFaQ&e=",
        ):
            with self.subTest(link):
                self.assertFalse(is_sensitive_url(link))
                self.assertEqual(scrub_links(f"Doc {link} ok"), f"Doc {link} ok")
