"""Personal links in shapes the scrubber once missed: the site's SMS short link (``/l/<token>``, personal only on the
site's own hosts, so Teams' ``/l/meetup-join/…`` stays), a link JSON-escaped (``https:\\/\\/…``), and a link wrapped
by Proofpoint URL Defense (v2's "-XX" and "_", v3's "*" marks), which goes whole like a Safe Links wrapper. And
ordinary links the token-shaped backstop once broke: one a gateway wrapped (judged by the link it holds, the gateway's
own parameters as written; also Safe Links' form for a link that opens in an app) and a Microsoft Forms link (its
``id=`` names the form)."""

from urllib.parse import quote

from django.test import SimpleTestCase, override_settings

from apps.core.services.email.inbound import LINK_PLACEHOLDER as REMOVED
from apps.core.services.email.inbound import is_sensitive_url, scrub_links, scrub_personal_links, scrub_subject
from apps.core.services.email.inbound.processing.scrub import readings

from .test_scrub_runs import DOCS, SIGN_IN, TOKEN, UNSUBSCRIBE

SMS = "https://i2g.ucmerced.edu/l/SmSsHoRt7kQ2pRt4sQ9pXw"  # FRONTEND_URL + "/l/" + secrets.token_urlsafe(16)
TEAMS = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_NjQ5ZDY4YTktYzQ1%40thread.v2/0?context=%7b%7d"
PROOFPOINT_V2 = (
    "https://urldefense.proofpoint.com/v2/url?u=https-3A__i2g.ucmerced.edu_login-2Dlink-23token-3D"
    f"{TOKEN.replace('-', '-2D')}&d=DwMFaQ&c=AbCd&r=EfGh&m=IjKl&s=MnOp&e="
)
PROOFPOINT_V3 = f"https://urldefense.com/v3/__{SIGN_IN.replace('#', '*')}__;Iw!!AbCdEf!ghIjKl$"  # "Iw": "#"
# Microsoft Safe Links as it wraps a link now: "data=" names the recipient and carries base64 mail-flow details.
SAFE_LINKS_DATA = (
    "&data=05%7C02%7Cpat%40ucmerced.edu%7C3c2f1a9b8e7d4c6b5a4908f7e6d5c4b3%7C0d3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b%7C0%7C0"
    "%7C638674123456789012%7CUnknown%7CTWFpbGZsb3d8eyJFbXB0eU1hcGkiOnRydWUsIlYiOiIwLjAuMDAwMCIsIlAiOiJXaW4zMiIsIkFO"
    "IjoiTWFpbCIsIldUIjoyfQ%3D%3D%7C0%7C%7C%7C&sdata=Xy7%2BAbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbC%3D&reserved=0"
)
MEETING = (  # its meeting id, encoded once more inside Safe Links' "url=", is a 60-character run
    "https://teams.microsoft.com/l/meetup-join/19%3ameeting_NjQ5ZmY4MDYtOTM5Mi00NDcwLWI4MDctMjQ3ZGM0NzYyZjc1"
    "%40thread.v2/0?context=%7b%22Tid%22%3a%22e1f2a3b4-c5d6-7e8f-9a0b-1c2d3e4f5a6b%22%7d"
)
LONG_DOC = (
    "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefghijk/edit?usp=sharing&tab=t.0"
)
FORM = (
    "https://forms.office.com/Pages/ResponsePage.aspx?id=DQSIkWdsW0yxEjajBLZtrQAAAAAAAAAAAAN__q9kZ0FUNkdXMFdRNjNBWUFF"
    "NE9TVjRMMEtQWjNQOS4u"
)


def json_escaped(value: str) -> str:
    """``value`` as a JSON writer that escapes "/" (PHP's ``json_encode``) writes it."""
    return value.replace("/", "\\/")


def safe_links(link: str) -> str:
    """``link`` as Microsoft Safe Links wraps it."""
    return f"https://nam12.safelinks.protection.outlook.com/?url={quote(link, safe='')}{SAFE_LINKS_DATA}"


def proofpoint_v2(link: str) -> str:
    """``link`` as Proofpoint URL Defense v2 wraps it: letters, digits and "." as written, "_" for "/", "-XX" else."""
    held = "".join(
        c if c.isascii() and (c.isalnum() or c == ".") else "_" if c == "/" else f"-{ord(c):02X}" for c in link
    )
    return (
        f"https://urldefense.proofpoint.com/v2/url?u={held}&d=DwMFaQ&c=euGZstcaTDllvimEN8b7jXrwqOf-v5A_CdpgnVfiiMM&e="
    )


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

    def test_a_proofpoint_v3_wrapper_reads_as_the_link_it_holds_without_its_own_tail(self):
        # The helpdesk reads the host a Mimecast link goes to from its "domain=": the "!!…$" tail once stuck to it.
        mimecast = "https://protect-us.mimecast.com/s/r1BdC8qQ0f?domain=i2g.ucmerced.edu"

        self.assertEqual(list(readings(f"https://urldefense.com/v3/__{mimecast}__;!!AbCdEf!ghIjKl$")), [mimecast])


class GatewayBackstopTests(SimpleTestCase):
    def test_an_ordinary_link_a_gateway_wrapped_and_a_forms_link_stay_whole(self):
        # The backstop cut a 60-character run out of Safe Links' "data=", the meeting id, v2's one-run path, v3's
        # signature and the form's id, and each link broke: on the ticket page (an href) as in the text.
        v3 = f"https://urldefense.com/v3/__{LONG_DOC}__;!!G_uCfscf7eWS!{'ZVz4e4tQ5u' * 7}$"
        wrapped = (
            safe_links(MEETING),
            safe_links(LONG_DOC),
            proofpoint_v2(LONG_DOC),
            v3,
            safe_links(proofpoint_v2(FORM)),
        )
        for link in (*wrapped, FORM):
            with self.subTest(link):
                self.assertEqual(scrub_links(f"Join: {link} today"), f"Join: {link} today")
                markup = f'<a href="{link.replace("&", "&amp;")}">join</a>'
                self.assertEqual(scrub_links(markup), markup)

    def test_a_safe_links_wrapper_of_a_link_that_opens_in_an_app_is_judged_by_the_link_it_holds(self):
        # For a Teams meeting or an Office file Safe Links writes the app's path before "?url=": read as no wrapper,
        # the link lost the meeting id, the form id and runs of "data=" to [redacted], and broke.
        for app, link in (("t", MEETING), ("w", LONG_DOC), ("x", FORM)):
            wrapped = safe_links(link).replace(".com/?url=", f".com/ap/{app}-59584e83/?url=")
            with self.subTest(app):
                self.assertEqual(scrub_links(f"Join: {wrapped} today"), f"Join: {wrapped} today")
                markup = f'<a href="{wrapped.replace("&", "&amp;")}">join</a>'
                self.assertEqual(scrub_links(markup), markup)
        personal = safe_links(SIGN_IN).replace(".com/?url=", ".com/ap/t-59584e83/?url=")
        self.assertEqual(scrub_links(f"Open {personal} now"), f"Open {REMOVED} now")

    def test_inside_a_wrapper_a_personal_link_or_a_token_shaped_segment_still_goes(self):
        opaque = "https://files.example/get?id=" + "Q" * 70 + "&x=1"  # another site's opaque token
        cut = "https://files.example/get?key=" + "A" * 30 + "+" + "B" * 35  # Safe Links writes "%2B": two short runs

        self.assertEqual(scrub_links(f"Open {safe_links(SIGN_IN)} now"), f"Open {REMOVED} now")
        self.assertEqual(scrub_links(safe_links(opaque)), safe_links(opaque).replace("%3D" + "Q" * 70, "%[redacted]"))
        self.assertEqual(scrub_links(safe_links(cut)), safe_links(cut).replace(quote(cut, safe=""), "[redacted]"))
        # What follows the gateway's own parameters (a row's next cell) is judged as any link's text.
        self.assertEqual(scrub_links(f"{safe_links(DOCS)},{'T' * 70},Pat"), f"{safe_links(DOCS)},[redacted],Pat")
