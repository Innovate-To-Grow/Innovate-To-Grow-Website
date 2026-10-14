import logging
from dataclasses import dataclass

from django.contrib import auth
from django.shortcuts import redirect

from apps.authn.services.email.challenges.queries import latest_pending_for_input
from apps.authn.services.send_verification import (
    OP_ADMIN_LOGIN_REMEMBERED_CODE,
    OP_ADMIN_LOGIN_REQUEST_CODE,
    OP_ADMIN_LOGIN_RESEND,
    fingerprint_payload,
)
from apps.authn.services.send_verification.constants import EMAIL_CHANNEL, KIND_EMAIL
from apps.authn.services.send_verification.http import guarded_send
from apps.authn.services.send_verification.outcomes import active_send_request_id
from apps.authn.views.admin.login_helpers import (
    clear_admin_login_session,
    get_admin_login_state,
    get_admin_member_display_name,
    get_last_admin_login_member,
    get_unresolved_admin_send,
    render_admin_login,
    safe_admin_next,
    set_admin_login_state,
    set_last_admin_login_cookie,
)

logger = logging.getLogger(__name__)


RECENT_CODE_HINT = "If a code already reached this address, enter the most recent one below."


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
    previous_step, previous_email, previous_member_id = get_admin_login_state(request)

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
        request.session.pop("admin_send_unresolved_request_id", None)
        if previous_step == "code":
            set_admin_login_state(
                request,
                step=previous_step,
                email=previous_email,
                member_id=previous_member_id,
            )
        elif not recent_code:
            clear_admin_login_session(request)
    if response.status_code >= 500:
        return AdminSendRefused("Failed to send verification code. Please try again later.")
    detail = response.data.get("detail") or "Failed to send verification code. Please try again later."
    return AdminSendRefused(str(detail), recent_code=recent_code)


class EmailCodeLoginMixin:
    # noinspection PyMethodMayBeStatic
    def _handle_email_step(self, request):
        import apps.authn.views.admin.login as login_api

        form = login_api.AdminEmailForm(request.POST)
        if not form.is_valid():
            return render_admin_login(request, step="email", form=form)

        member = form.cleaned_data["member"]
        email = form.cleaned_data["email"]
        refused = _admin_send_code(
            request,
            operation=OP_ADMIN_LOGIN_REQUEST_CODE,
            member=member,
            email=email,
            hide_email=False,
        )
        if refused and not refused.recent_code:
            form.add_error(None, refused.message)
            return render_admin_login(request, step="email", form=form)

        set_admin_login_state(
            request,
            step="code",
            email=email,
            member_id=str(member.pk),
            hide_email=False,
        )
        return render_admin_login(
            request,
            step="code",
            email=email,
            form=login_api.AdminCodeForm(),
            message=(
                f"{refused.message} {RECENT_CODE_HINT}"
                if refused
                else "A verification code has been sent to your email."
            ),
        )

    def _handle_remembered_code_step(self, request):
        import apps.authn.views.admin.login as login_api

        member = get_last_admin_login_member(request)
        contact = member.get_primary_contact_email() if member else None
        if member is None or contact is None or not contact.verified:
            return render_admin_login(
                request,
                step="email",
                form=login_api.AdminEmailForm(),
                error="Unable to send verification code.",
            )

        refused = _admin_send_code(
            request,
            operation=OP_ADMIN_LOGIN_REMEMBERED_CODE,
            member=member,
            email=contact.email_address,
            hide_email=True,
        )
        if refused and not refused.recent_code:
            return render_admin_login(
                request,
                step="email",
                form=login_api.AdminEmailForm(),
                error=refused.message,
            )

        set_admin_login_state(
            request,
            step="code",
            email=contact.email_address,
            member_id=str(member.pk),
            hide_email=True,
        )
        return render_admin_login(
            request,
            step="code",
            email=contact.email_address,
            form=login_api.AdminCodeForm(),
            message=(
                f"{refused.message} {RECENT_CODE_HINT}"
                if refused
                else f"A verification code has been sent to {get_admin_member_display_name(member)}."
            ),
        )

    def _handle_code_step(self, request):
        import apps.authn.views.admin.login as login_api

        _, email, member_id = get_admin_login_state(request)
        if not email or not member_id:
            clear_admin_login_session(request)
            return render_admin_login(request, step="email", form=login_api.AdminEmailForm())

        if request.POST.get("action") == "resend":
            return self._handle_resend(request, email, member_id)

        form = login_api.AdminCodeForm(request.POST)
        if not form.is_valid():
            return render_admin_login(request, step="code", email=email, form=form)

        try:
            challenge = login_api.verify_email_code(
                purpose=login_api.PURPOSE,
                target_email=email,
                code=form.cleaned_data["code"],
            )
        except login_api.AuthChallengeInvalid:
            form.add_error(None, "Verification code is invalid or has expired.")
            return render_admin_login(request, step="code", email=email, form=form)

        member = challenge.member
        if not member.is_staff or not member.is_active:
            clear_admin_login_session(request)
            return render_admin_login(
                request,
                step="email",
                form=login_api.AdminEmailForm(),
                error="You do not have access to the admin panel.",
            )

        auth.login(request, member, backend="apps.authn.security.backends.EmailAuthBackend")
        clear_admin_login_session(request)
        logger.info("Admin login via email code: %s", member.get_primary_email())
        response = redirect(safe_admin_next(request))
        return set_last_admin_login_cookie(response, member)

    # noinspection PyMethodMayBeStatic
    def _handle_resend(self, request, email, member_id):
        import apps.authn.views.admin.login as login_api

        member = login_api.Member.objects.filter(
            pk=member_id,
            is_staff=True,
            is_active=True,
        ).first()
        if not member:
            clear_admin_login_session(request)
            return render_admin_login(request, step="email", form=login_api.AdminEmailForm())

        refused = _admin_send_code(
            request,
            operation=OP_ADMIN_LOGIN_RESEND,
            member=member,
            email=email,
        )
        message = "A new verification code has been sent." if refused is None else refused.message
        return render_admin_login(
            request,
            step="code",
            email=email,
            form=login_api.AdminCodeForm(),
            message=message,
        )
