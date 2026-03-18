"""
Two-step admin login via email verification code (plain Django view, not DRF).
"""

import logging

from django.contrib import admin, auth
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.cache import never_cache

from authn.forms.admin_login import AdminCodeForm, AdminEmailForm
from authn.models.security import EmailAuthChallenge
from authn.services.email_challenges import (
    AuthChallengeDeliveryError,
    AuthChallengeInvalid,
    AuthChallengeThrottled,
    consume_login_or_registration_challenge,
    issue_email_challenge,
    verify_email_code,
)

logger = logging.getLogger(__name__)

Member = get_user_model()

_SESSION_STEP = "admin_login_step"
_SESSION_EMAIL = "admin_login_email"
_SESSION_MEMBER_ID = "admin_login_member_id"

PURPOSE = EmailAuthChallenge.Purpose.ADMIN_LOGIN


def _clear_session(request):
    for key in (_SESSION_STEP, _SESSION_EMAIL, _SESSION_MEMBER_ID):
        request.session.pop(key, None)


def _admin_context(request, **extra):
    ctx = admin.site.each_context(request)
    ctx["site_title"] = admin.site.site_title
    ctx["site_header"] = admin.site.site_header
    ctx["title"] = "Log in"
    ctx.update(extra)
    return ctx


def _safe_next(request):
    next_url = request.GET.get("next") or request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return "/admin/"


@method_decorator(never_cache, name="dispatch")
class AdminLoginView(View):
    """Passwordless admin login: email → SES code → verify → login."""

    def get(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            return redirect(_safe_next(request))

        # Allow resetting back to email step
        if request.GET.get("step") == "email":
            _clear_session(request)

        step = request.session.get(_SESSION_STEP, "email")
        if step == "code":
            email = request.session.get(_SESSION_EMAIL, "")
            return render(
                request, "admin/login.html", _admin_context(request, step="code", email=email, form=AdminCodeForm())
            )
        return render(request, "admin/login.html", _admin_context(request, step="email", form=AdminEmailForm()))

    def post(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            return redirect(_safe_next(request))

        step = request.session.get(_SESSION_STEP, "email")
        if step == "code":
            return self._handle_code_step(request)
        return self._handle_email_step(request)

    # ── step 1: email ───────────────────────────────────────────────

    def _handle_email_step(self, request):
        form = AdminEmailForm(request.POST)
        if not form.is_valid():
            return render(request, "admin/login.html", _admin_context(request, step="email", form=form))

        member = form.cleaned_data["member"]
        email = form.cleaned_data["email"]

        try:
            issue_email_challenge(member=member, purpose=PURPOSE, target_email=email)
        except AuthChallengeThrottled as exc:
            form.add_error(None, str(exc))
            return render(request, "admin/login.html", _admin_context(request, step="email", form=form))
        except AuthChallengeDeliveryError:
            form.add_error(None, "Failed to send verification code. Please try again later.")
            return render(request, "admin/login.html", _admin_context(request, step="email", form=form))

        request.session[_SESSION_STEP] = "code"
        request.session[_SESSION_EMAIL] = email
        request.session[_SESSION_MEMBER_ID] = str(member.pk)

        return render(
            request,
            "admin/login.html",
            _admin_context(
                request,
                step="code",
                email=email,
                form=AdminCodeForm(),
                message="A verification code has been sent to your email.",
            ),
        )

    # ── step 2: code ────────────────────────────────────────────────

    def _handle_code_step(self, request):
        email = request.session.get(_SESSION_EMAIL)
        member_id = request.session.get(_SESSION_MEMBER_ID)

        if not email or not member_id:
            _clear_session(request)
            return render(request, "admin/login.html", _admin_context(request, step="email", form=AdminEmailForm()))

        # Resend action
        if request.POST.get("action") == "resend":
            return self._handle_resend(request, email, member_id)

        form = AdminCodeForm(request.POST)
        if not form.is_valid():
            return render(request, "admin/login.html", _admin_context(request, step="code", email=email, form=form))

        code = form.cleaned_data["code"]

        try:
            challenge = verify_email_code(purpose=PURPOSE, target_email=email, code=code)
        except AuthChallengeInvalid:
            form.add_error(None, "Verification code is invalid or has expired.")
            return render(request, "admin/login.html", _admin_context(request, step="code", email=email, form=form))

        consume_login_or_registration_challenge(challenge)

        member = challenge.member
        if not member.is_staff or not member.is_active:
            _clear_session(request)
            return render(
                request,
                "admin/login.html",
                _admin_context(
                    request, step="email", form=AdminEmailForm(), error="You do not have access to the admin panel."
                ),
            )

        auth.login(request, member, backend="authn.backends.EmailOrUsernameBackend")
        _clear_session(request)
        logger.info("Admin login via email code: %s", member.email)
        return redirect(_safe_next(request))

    def _handle_resend(self, request, email, member_id):
        member = Member.objects.filter(pk=member_id, is_staff=True, is_active=True).first()
        if not member:
            _clear_session(request)
            return render(request, "admin/login.html", _admin_context(request, step="email", form=AdminEmailForm()))

        try:
            issue_email_challenge(member=member, purpose=PURPOSE, target_email=email)
            message = "A new verification code has been sent."
        except AuthChallengeThrottled as exc:
            message = str(exc)
        except AuthChallengeDeliveryError:
            message = "Failed to send verification code. Please try again later."

        return render(
            request,
            "admin/login.html",
            _admin_context(request, step="code", email=email, form=AdminCodeForm(), message=message),
        )
