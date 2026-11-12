"""What switching a member's primary email means, in words: the confirmation page's notes and the messages after it.

What reads the primary (checked against the sign-in and audience code):

- Email-code and password sign-in accept any **verified** address of the member, whatever its type.
- Admin sign-in codes go only to a staff member's verified **primary**; password change/reset and account-deletion
  codes go to the verified primary first.
- "Primary email only" campaigns mail the primary: All subscribers only while it is subscribed; All active members,
  Staff and Selected members whatever its setting. "All emails" campaigns are not affected.
- Event registrations copied the address when they were made, so they keep it.
"""

from django.contrib import messages

from ...services.contacts.primary_switch import NOT_VERIFIED, PRIMARY, current_primary


def row_reason(email) -> str:
    """Why a row of the page offers no "Make primary" (short)."""
    return "Current primary" if email.email_type == PRIMARY else "Verify first"


def why_not(email) -> str:
    """Why ``email`` cannot become the primary (a full sentence)."""
    if email.email_type == PRIMARY:
        return f"{email.email_address} is already the primary email."
    return NOT_VERIFIED.format(address=email.email_address)


def _note(text: str, level: str = "info") -> dict:
    return {"text": text, "level": level}


def _sign_in(request, member, previous, target) -> list[str]:
    new = target.email_address
    if previous is None:
        both = f"{new} keeps working."
    elif previous.verified:
        both = f"both {previous.email_address} and {new} keep working."
    else:
        both = f"{new} keeps working, and {previous.email_address} (not verified) still does not."
    notes = [
        f"Signing in with an emailed code or a password works with any verified address, whatever its type: {both}"
    ]
    if member.is_staff:
        lost = f", and {previous.email_address} no longer receives them" if previous is not None else ""
        notes.append(f"Admin sign-in codes go only to a staff member's verified primary: from now on to {new}{lost}.")
        if member.pk == request.user.pk:
            notes.append(
                f"This is your own account: your next admin sign-in code goes to {new}. Check you can read it."
            )
    notes.append(
        f"Codes to change or reset the password, and to delete the account, go to the verified primary: {new}."
    )
    notes.append(f"The member's profile, the Members list, exports and the member sheet show {new} as the primary.")
    return notes


def _reached_before(previous) -> bool:
    """Whether "primary email only" campaigns to All subscribers reached the member before the switch."""
    return previous is not None and previous.subscribe


def _newsletters(previous, target) -> list[dict]:
    new = target.email_address
    advice = (
        f"The switch changes no subscription: tick Subscribed on {new} only if the member asked for newsletters there."
    )
    if not target.subscribe and _reached_before(previous):
        first = _note(
            f"{new} is unsubscribed ({previous.email_address} is subscribed): campaigns to All subscribers sent to the "
            f"primary email only will no longer reach this member. {advice}",
            "warning",
        )
    elif not target.subscribe:
        # Nothing changes here: the old primary was unsubscribed too, or there was none.
        first = _note(
            f"{new} is unsubscribed: campaigns to All subscribers sent to the primary email only did not reach this "
            f"member before the switch and still will not. {advice}"
        )
    elif previous is not None and not previous.subscribe:
        first = _note(
            f"{previous.email_address} is unsubscribed but {new} is subscribed: the member starts receiving campaigns "
            f"to All subscribers sent to the primary email only, at {new}. If they did not ask for newsletters, untick "
            f"Subscribed on {new}.",
            "warning",
        )
    else:
        first = _note(f"Campaigns to All subscribers sent to the primary email only go to {new} from now on.")
    rest = _note(
        f"All active members, Staff and Selected members campaigns sent to the primary email only also go to {new} "
        "(they ignore Subscribed). Campaigns sent to all of a member's addresses are not affected: each address keeps "
        "its own setting."
    )
    return [first, rest]


def _unchanged(previous) -> list[str]:
    notes = [
        "No address is verified, unverified, subscribed or unsubscribed, nothing is deleted, and nothing is sent to "
        "either address."
    ]
    if previous is not None:
        old = previous.email_address
        notes.append(f"Event registrations keep the address they were made with: tickets issued to {old} stay there.")
        if previous.verified:
            notes.append(f"To undo, switch back: {old} stays verified (as the secondary).")
        else:
            notes.append(f"{old} is not verified, so it cannot be made the primary again until it is verified.")
    return notes


def _bounce_tip(previous) -> str:
    if previous is None:
        return ""
    return (
        f"Switching because {previous.email_address} bounces? Campaigns sent to all of a member's addresses still mail "
        "it. To stop that, mark it undeliverable in Email Monitoring → Bounced addresses (sign-in codes still reach "
        "it); to stop only newsletters, untick its Subscribed."
    )


def switch_notes(request, member, emails, target) -> dict:
    """The confirmation page's notes for making ``target`` the primary."""
    previous = current_primary(emails)
    return {
        "sign_in": _sign_in(request, member, previous, target),
        "newsletters": _newsletters(previous, target),
        "unchanged": _unchanged(previous),
        "bounce": _bounce_tip(previous),
    }


def outcome_messages(result) -> list[tuple[int, str]]:
    """The messages shown on the member page after a switch (``result``: a ``PrimarySwitch``)."""
    new = result.primary.email_address
    if not result.changed:
        return [(messages.INFO, f"{new} is already the primary email. Nothing was changed.")]
    moved = f" {result.previous.email_address} is now the secondary." if result.previous is not None else ""
    out = [
        (
            messages.SUCCESS,
            f"{new} is now the primary email of {result.member}.{moved} No subscription or verification changed, and "
            "nothing was sent.",
        )
    ]
    if not result.primary.subscribe and _reached_before(result.previous):
        out.append(
            (
                messages.WARNING,
                f"{new} is unsubscribed, so campaigns to All subscribers sent to the primary email only no longer "
                "reach this member.",
            )
        )
    return out
