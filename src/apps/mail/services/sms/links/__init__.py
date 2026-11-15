"""SMS short links (``/l/<token>``): issuing the tokens behind ``{{login_link}}``, ``{{ticket_link}}`` and
``{{event_link}}``, and exchanging one when it is opened.

A token is ``SMS_POLICY["link_token_bytes"]`` random bytes (128 bits by default, 22 URL-safe characters), so the URL
holds no member, phone or event and cannot be guessed. Only its SHA-256 digest is stored, except for a shared link,
which signs nobody in. Every link expires; a personal one signs its member in once (``first_used_at`` is claimed
with one conditional UPDATE, so two clicks cannot both sign in) and is never issued to staff, a superuser or an
inactive member.

A personal link reaches no further than signing in with a code texted to the same number would: it is issued only
when the number it is texted to is the member's own verified account phone, and opening it checks that the member
still has that phone (``phone_digest``). Any other recipient gets a link that opens the sign-in page. Destinations
must pass ``is_strict_internal_path`` (the SPA's own rule). Opening a link is limited by the request limiter's
``auth-email-link`` scope.

Turning personal sign-in links off (or links in SMS) revokes every outstanding one for good (``SmsConfig.save``
settles them in its transaction). A personal link carries the SMS Settings epoch it was issued in, read together with
the switches, and signs in only while that epoch is current and it was never revoked: turning the switch on again
brings none back, and one stored while the switch was going off is dead on arrival. A revoked personal link, or any
personal link while they are off, opens the sign-in page with its return path and signs nobody in. Shared links
are no credential and are not affected.
"""

from .issuing import (
    EVENT_PAGE_PATH,
    LINK_PATH,
    SIGN_IN_PATH,
    TOKEN_RE,
    Purpose,
    event_page_path,
    example_link,
    issue_personal_link,
    issue_redirect_link,
    link_url,
    may_sign_in_by_sms,
    may_text_personal_link,
    member_owns_phone,
    personal_link_state,
    phone_digest,
    revoke_links,
    shared_link,
    sign_in_path,
    token_digest,
)
from .opening import Opened, open_link
