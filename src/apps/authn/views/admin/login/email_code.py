import logging

from django.contrib import auth
from django.shortcuts import redirect

from apps.authn.services.send_verification import (
    OP_ADMIN_LOGIN_REMEMBERED_CODE,
    OP_ADMIN_LOGIN_REQUEST_CODE,
    OP_ADMIN_LOGIN_RESEND,
)

from .code_sending import _admin_send_code
from .page import render_admin_login
from .state import (
    clear_admin_login_session,
    get_admin_login_state,
    get_admin_member_display_name,
    get_last_admin_login_member,
    safe_admin_next,
    set_admin_login_state,
    set_last_admin_login_cookie,
)

logger = logging.getLogger(__name__)


RECENT_CODE_HINT = "If a code already reached this address, enter the most recent one below."


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
