"""Personal sign-in links in what staff write (a note, a reply) and in a requester's text files: only those links go,
every other link and the text around them is kept as written. The rule is core's (``scrub_personal_links``), the one
inbound mail is scrubbed by, so a link loses the same characters wherever it is pasted."""

from apps.core.services.email.inbound import scrub_personal_links


def scrub_sign_in_links(value) -> str:
    """Text staff write (a note, a reply) or a text file with only the site's personal sign-in and subscription links
    replaced: every other link is kept as written, long ones included, and so is the text right after a link."""
    return scrub_personal_links(value)
