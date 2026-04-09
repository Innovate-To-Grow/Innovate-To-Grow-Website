"""Helpers for the admin login view."""

from django.contrib import admin
from django.core.cache import cache
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme

_SESSION_STEP = "admin_login_step"
_SESSION_EMAIL = "admin_login_email"
_SESSION_MEMBER_ID = "admin_login_member_id"
_RATE_LIMIT_PREFIX = "admin_pwd_login:"
_MAX_PASSWORD_ATTEMPTS = 10
_RATE_LIMIT_WINDOW = 120


def clear_admin_login_session(request):
    for key in (_SESSION_STEP, _SESSION_EMAIL, _SESSION_MEMBER_ID):
        request.session.pop(key, None)


def get_admin_login_state(request):
    return (
        request.session.get(_SESSION_STEP, "email"),
        request.session.get(_SESSION_EMAIL, ""),
        request.session.get(_SESSION_MEMBER_ID),
    )


def set_admin_login_state(request, *, step: str, email: str, member_id: str | None = None) -> None:
    request.session[_SESSION_STEP] = step
    request.session[_SESSION_EMAIL] = email
    if member_id is not None:
        request.session[_SESSION_MEMBER_ID] = member_id


def safe_admin_next(request):
    next_url = request.GET.get("next") or request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return "/admin/"


def is_password_throttled(request):
    return cache.get(_password_rate_key(request), 0) >= _MAX_PASSWORD_ATTEMPTS


def record_password_failure(request):
    key = _password_rate_key(request)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, _RATE_LIMIT_WINDOW)


def clear_password_rate_limit(request):
    cache.delete(_password_rate_key(request))


def render_admin_login(request, *, form, step: str, email: str = "", **extra):
    next_param = request.GET.get("next", "")
    next_qs = f"&next={next_param}" if next_param else ""
    context = admin.site.each_context(request)
    context.update(
        {
            "site_title": admin.site.site_title,
            "site_header": admin.site.site_header,
            "title": "Log in",
            "password_mode_url": f"?mode=password{next_qs}",
            "email_code_mode_url": f"?step=email{next_qs}",
            "step": step,
            "form": form,
            "email": email,
        }
    )
    context.update(extra)
    return render(request, "admin/login.html", context)


def _password_rate_key(request):
    return f"{_RATE_LIMIT_PREFIX}{request.META.get('REMOTE_ADDR', 'unknown')}"
