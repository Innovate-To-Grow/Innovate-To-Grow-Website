"""Labels and help text for the account flag and the per-address flags, shared by every Members admin form.

They are set on the admin forms (``Meta.labels`` / ``Meta.help_texts``, which Django also uses for read-only fields),
not on the models, so changing them needs no migration. What each flag does:

- **Account active** (``Member.is_active``) is the account: signing in at all, and the All subscribers, All active
  members and Staff audiences. It is independent of the contact flags: turning it off changes no address or phone,
  and no contact flag changes it.
- **Verified** (per email address or phone) is a way to sign in. It does not decide who gets mail.
- **Subscribed** (per email address) is read only by the All subscribers audience (newsletters).
"""

ACCOUNT_ACTIVE_LABEL = "Account active"
ACCOUNT_ACTIVE = (
    "The member can sign in, and is included in the All subscribers, All active members and Staff audiences. Turning "
    "it off changes no email address or phone number. It is not the tool for a bounced address: to stop campaign "
    "mail to one address, use Email Monitoring → Bounced addresses → Mark undeliverable (or untick Subscribed on that "
    "address for newsletters only)."
)
UNFINISHED_SIGN_UP_LABEL = "Unfinished sign-up"
UNFINISHED_SIGN_UP = (
    "The person started a self-service sign-up and never finished it, so the account is not active yet. It ends the "
    "first time the account is activated, or with the list action “Deactivate selected members” (the person then can "
    "no longer finish the sign-up)."
)

EMAIL_TYPE = (
    "Primary: the member's main address (campaigns sent to the primary email only; a staff member's admin sign-in "
    "codes). Secondary: a backup address. Other: any further address. To make another verified address the primary, "
    "use “Switch primary email” on the member page."
)
EMAIL_VERIFIED = (
    "The person proved they receive mail here (they entered a code sent to it), or staff confirmed it. A verified "
    "address can be used to sign in and can become the primary; a staff member's admin sign-in codes go to their "
    "verified primary only. Unticking it stops sign-in with this address. It does not stop any mail."
)
EMAIL_SUBSCRIBED = (
    "Receives newsletters: the All subscribers audience (campaigns sent to the primary email only use the primary's "
    "setting). All active members, Staff, Selected members and event audiences ignore it. Sign-in codes and other "
    "account mail are never affected."
)
PHONE_SUBSCRIBED = (
    "Receives SMS campaigns that need opt-in (the Subscribers audience, or the “verified and opted in” policy). "
    "Replying STOP turns it off."
)

EMAIL_LABELS = {"verified": "Verified (sign-in)", "subscribe": "Subscribed (newsletters)"}
EMAIL_HELP_TEXTS = {"email_type": EMAIL_TYPE, "verified": EMAIL_VERIFIED, "subscribe": EMAIL_SUBSCRIBED}
MEMBER_LABELS = {"is_active": ACCOUNT_ACTIVE_LABEL, "registration_pending": UNFINISHED_SIGN_UP_LABEL}
MEMBER_HELP_TEXTS = {"is_active": ACCOUNT_ACTIVE, "registration_pending": UNFINISHED_SIGN_UP}
