"""
Admin login via email verification code or password (plain Django view, not DRF).
"""

import logging

from django.contrib import auth
from django.contrib.auth import authenticate, get_user_model
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from authn.forms.admin_login import AdminCodeForm, AdminEmailForm, AdminPasswordForm
from authn.models.security import EmailAuthChallenge
from authn.services.email_challenges import (
    AuthChallengeDeliveryError,
    AuthChallengeInvalid,
    AuthChallengeThrottled,
    consume_login_or_registration_challenge,
    issue_email_challenge,
    verify_email_code,
)
from authn.views.admin_login_helpers import (
    clear_admin_login_session,
    clear_password_rate_limit,
    get_admin_login_state,
    is_password_throttled,
    record_password_failure,
    render_admin_login,
    safe_admin_next,
    set_admin_login_state,
)

logger = logging.getLogger(__name__)

Member = get_user_model()

PURPOSE = EmailAuthChallenge.Purpose.ADMIN_LOGIN


@method_decorator(never_cache, name="dispatch")
class AdminLoginView(View):
    """Admin login: email code flow OR password flow."""

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            return redirect(safe_admin_next(request))

        if request.GET.get("mode") == "password":
            clear_admin_login_session(request)
            return render_admin_login(request, step="password", form=AdminPasswordForm())

        if request.GET.get("step") == "email":
            clear_admin_login_session(request)

        step, email, _ = get_admin_login_state(request)
        if step == "code":
            return render_admin_login(request, step="code", email=email, form=AdminCodeForm())
        return render_admin_login(request, step="email", form=AdminEmailForm())

    def post(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            return redirect(safe_admin_next(request))

        if request.POST.get("mode") == "password":
            return self._handle_password_step(request)

        step, _, _ = get_admin_login_state(request)
        if step == "code":
            return self._handle_code_step(request)
        return self._handle_email_step(request)

    # ── password login ────────────────────────────────────────────────

    # noinspection PyMethodMayBeStatic
    def _handle_password_step(self, request):
        if is_password_throttled(request):
            form = AdminPasswordForm(request.POST)
            form.add_error(None, "Too many login attempts. Please try again later.")
            return render_admin_login(request, step="password", form=form)

        form = AdminPasswordForm(request.POST)
        if not form.is_valid():
            return render_admin_login(request, step="password", form=form)

        email = form.cleaned_data["email"].strip().lower()
        password = form.cleaned_data["password"]

        member = authenticate(request, username=email, password=password)
        if member is None or not member.is_staff or not member.is_active:
            record_password_failure(request)
            form.add_error(None, "Invalid email or password.")
            return render_admin_login(request, step="password", form=form)

        clear_password_rate_limit(request)
        auth.login(request, member, backend="authn.backends.EmailAuthBackend")
        clear_admin_login_session(request)
        logger.info("Admin login via password: %s", member.get_primary_email())
        return redirect(safe_admin_next(request))

    # ── step 1: email ───────────────────────────────────────────────

    # noinspection PyMethodMayBeStatic
    def _handle_email_step(self, request):
        form = AdminEmailForm(request.POST)
        if not form.is_valid():
            return render_admin_login(request, step="email", form=form)

        member = form.cleaned_data["member"]
        email = form.cleaned_data["email"]

        try:
            issue_email_challenge(member=member, purpose=PURPOSE, target_email=email)
        except AuthChallengeThrottled as exc:
            form.add_error(None, str(exc))
            return render_admin_login(request, step="email", form=form)
        except AuthChallengeDeliveryError:
            form.add_error(None, "Failed to send verification code. Please try again later.")
            return render_admin_login(request, step="email", form=form)

        set_admin_login_state(request, step="code", email=email, member_id=str(member.pk))
        return render_admin_login(
            request,
            step="code",
            email=email,
            form=AdminCodeForm(),
            message="A verification code has been sent to your email.",
        )

    # ── step 2: code ────────────────────────────────────────────────

    def _handle_code_step(self, request):
        _, email, member_id = get_admin_login_state(request)
        if not email or not member_id:
            clear_admin_login_session(request)
            return render_admin_login(request, step="email", form=AdminEmailForm())

        # Resend action
        if request.POST.get("action") == "resend":
            return self._handle_resend(request, email, member_id)

        form = AdminCodeForm(request.POST)
        if not form.is_valid():
            return render_admin_login(request, step="code", email=email, form=form)

        code = form.cleaned_data["code"]

        try:
            challenge = verify_email_code(purpose=PURPOSE, target_email=email, code=code)
        except AuthChallengeInvalid:
            form.add_error(None, "Verification code is invalid or has expired.")
            return render_admin_login(request, step="code", email=email, form=form)

        consume_login_or_registration_challenge(challenge)

        member = challenge.member
        if not member.is_staff or not member.is_active:
            clear_admin_login_session(request)
            return render_admin_login(
                request,
                step="email",
                form=AdminEmailForm(),
                error="You do not have access to the admin panel.",
            )

        auth.login(request, member, backend="authn.backends.EmailAuthBackend")
        clear_admin_login_session(request)
        logger.info("Admin login via email code: %s", member.get_primary_email())
        return redirect(safe_admin_next(request))

    # noinspection PyMethodMayBeStatic
    def _handle_resend(self, request, email, member_id):
        member = Member.objects.filter(pk=member_id, is_staff=True, is_active=True).first()
        if not member:
            clear_admin_login_session(request)
            return render_admin_login(request, step="email", form=AdminEmailForm())

        try:
            issue_email_challenge(member=member, purpose=PURPOSE, target_email=email)
            message = "A new verification code has been sent."
        except AuthChallengeThrottled as exc:
            message = str(exc)
        except AuthChallengeDeliveryError:
            message = "Failed to send verification code. Please try again later."

        return render_admin_login(request, step="code", email=email, form=AdminCodeForm(), message=message)
