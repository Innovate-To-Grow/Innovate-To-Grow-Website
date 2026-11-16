"""Sending the admin sign-in code: the protected send, and the refusal the form shows when it is not sent."""

from dataclasses import dataclass

from apps.authn.services.email.challenges.queries import latest_pending_for_input
from apps.authn.services.send_verification import (
    fingerprint_payload,
)
from apps.authn.services.send_verification.guard.http import guarded_send
from apps.authn.services.send_verification.guard.outcomes import active_send_request_id
from apps.authn.services.send_verification.rules.constants import EMAIL_CHANNEL, KIND_EMAIL

from .page import get_unresolved_admin_send
from .state import (
    clear_admin_login_session,
    get_admin_login_state,
    set_admin_login_state,
)


@dataclass(frozen=True)
class AdminSendRefused:
    """Why a login code was not sent.

    ``recent_code`` means the send was refused by the per-address limits (cooldown or hourly cap) while an
    admin-login code for this address is still usable, whoever asked for it. The caller then opens the code step
    anyway, so the mailbox owner can sign in with the code they hold instead of being held on the email step by
    someone else's requests. It is set only when such a code exists: the limits are shared by every code
    endpoint, and a sign-in code of another kind would not be accepted here. Opening the step gives nothing
    extra: a code is still required, and its guesses are counted per code as always.

    This narrows one lever, it does not remove it: wrong guesses from any session still use up a pending code
    (silently: a refused request made while a code is usable opens the step without sending anything), and
    requests through other code endpoints still hold the limits. It also means the refusal differs by whether
    this address has an admin code pending, which tells a caller when that is the case and nothing else. The
    remembered-admin password form is the path nobody else can interfere with.
    """

    message: str
    recent_code: bool = False


def _usable_admin_code_exists(email: str) -> bool:
    """Whether the code step could accept a code for ``email`` right now (the challenge verification would pick)."""
    import apps.authn.views.admin.login as login_api

    challenge = latest_pending_for_input(purposes=[login_api.PURPOSE], target_email=email)
    return challenge is not None and not challenge.is_expired and challenge.attempts < challenge.max_attempts


def _ensure_session(request):
    if not request.session.session_key:
        request.session.save()


def _restore_login_state(request, previous_state, *, keep_code_step: bool) -> None:
    """A refused send leaves the login where it was: the earlier code step, or cleared (unless a code is usable)."""
    previous_step, previous_email, previous_member_id = previous_state
    request.session.pop("admin_send_unresolved_request_id", None)
    if previous_step == "code":
        set_admin_login_state(request, step=previous_step, email=previous_email, member_id=previous_member_id)
    elif not keep_code_step:
        clear_admin_login_session(request)


def _admin_send_code(
    request, *, operation: str, member, email: str, hide_email: bool | None = None
) -> AdminSendRefused | None:
    """Consume a proof and send the admin login code; return ``None`` when sent, else why it was not.

    ``hide_email`` is what the code step must do with the address while this send is in flight or left unresolved
    (the state is saved before the mail provider is called): True for the remembered-admin flow, which shows the
    member's name instead, False for a typed address, ``None`` to keep whatever the session already says (resend).
    """
    import apps.authn.views.admin.login as login_api

    _ensure_session(request)
    previous = get_unresolved_admin_send(request)
    if previous is not None:
        return AdminSendRefused(
            "The previous send request is still unresolved. Check your messages and reload this page before sending again."
        )
    previous_state = get_admin_login_state(request)

    def perform():
        request.session["admin_send_unresolved_request_id"] = active_send_request_id()
        set_admin_login_state(request, step="code", email=email, member_id=str(member.pk), hide_email=hide_email)
        # Persist recovery context before the external call: a lost response or
        # process crash must not erase the original request reference.
        request.session.save()
        try:
            login_api.issue_email_challenge(
                member=member,
                purpose=login_api.PURPOSE,
                target_email=email,
            )
        except login_api.AuthChallengeThrottled as exc:
            return {"detail": str(exc)}, 429
        return {"detail": "sent"}, 202

    response = guarded_send(
        request,
        operation=operation,
        destination_kind=KIND_EMAIL,
        destination_normalized=email,
        fingerprint=fingerprint_payload({"email": email, "operation": operation}),
        channel=EMAIL_CHANNEL,
        perform=perform,
    )
    if response.data.get("code") == "send_unknown":
        request.session["admin_send_unresolved_request_id"] = response.data["request_id"]
        set_admin_login_state(request, step="code", email=email, member_id=str(member.pk), hide_email=hide_email)
    if 200 <= response.status_code < 300:
        request.session.pop("admin_send_unresolved_request_id", None)
        return None
    recent_code = response.status_code == 429 and _usable_admin_code_exists(email)
    if response.data.get("code") != "send_unknown":
        _restore_login_state(request, previous_state, keep_code_step=recent_code)
    if response.status_code >= 500:
        if response.data.get("retry_after") is not None:
            return AdminSendRefused(response.data["detail"])  # the delivery rate held it back: when to try again
        return AdminSendRefused("Failed to send verification code. Please try again later.")
    detail = response.data.get("detail") or "Failed to send verification code. Please try again later."
    return AdminSendRefused(str(detail), recent_code=recent_code)
