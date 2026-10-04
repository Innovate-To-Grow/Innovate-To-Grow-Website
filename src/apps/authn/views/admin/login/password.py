"""Password sign-in for the Django admin: the email + password form and the remembered-admin form.

Guessing is bounded by ``apps.authn.services.login_guard`` and never keyed on the client IP (staff share the campus
public IP, so an address-keyed counter locked every admin out together). The two forms count separately:

* The email + password form counts on the submitted email: the same counter as the member password login
  (``POST /authn/login/``), so an attacker does not get one allowance per entry point. Anyone who knows a staff
  address can therefore lock this form for it from anywhere, by failing on purpose. That is accepted: the address is
  the only thing an anonymous request can be counted by.
* The remembered-admin form posts no email; the account is the one in the signed, HttpOnly ``i2g_last_admin_member``
  cookie, which a browser only holds after signing in to the admin as that member. It counts on a
  ``login_guard.ScopedKey`` built from that member's id, a counter no typed identifier reaches on any endpoint. So
  failing for a staff address elsewhere never locks a returning admin's remembered form, and only a holder of the
  cookie can lock it (which leaves the email + password form open).

Either counter refuses before any password work, even with the correct password, and a success clears the counter
of the form that was used. The email-code admin login is not password based and is not affected by either.
"""

import logging

from django.contrib import auth
from django.contrib.auth import authenticate
from django.shortcuts import redirect

from apps.authn.services import login_guard
from apps.authn.views.admin.login_helpers import (
    clear_admin_login_session,
    get_last_admin_login_member,
    render_admin_login,
    safe_admin_next,
    set_last_admin_login_cookie,
)

logger = logging.getLogger(__name__)

LOCKED_ERROR = "Too many login attempts. Please try again later."

REMEMBERED_ADMIN_GUARD_SCOPE = "admin-remembered"


def remembered_admin_guard_key(member) -> login_guard.ScopedKey:
    """The ``login_guard`` counter of the remembered-admin form for ``member`` (the one in the signed cookie).

    Keyed on the member id alone: no client IP (staff share one), and not the member's email, which is public and
    would let anyone lock this form through an endpoint that takes a typed identifier.
    """
    return login_guard.ScopedKey(REMEMBERED_ADMIN_GUARD_SCOPE, str(member.pk))


class PasswordLoginMixin:
    # noinspection PyMethodMayBeStatic
    def _handle_password_step(self, request):
        import apps.authn.views.admin.login as login_api

        if request.POST.get("remembered_admin") == "1":
            return self._handle_remembered_password_step(request)

        form = login_api.AdminPasswordForm(request.POST)
        if not form.is_valid():
            return render_admin_login(request, step="password", form=form)

        email = form.cleaned_data["email"].strip().lower()
        if login_guard.retry_after(email):
            return _render_locked(request, form)

        member = authenticate(request, username=email, password=form.cleaned_data["password"])
        if member is None or not member.is_staff or not member.is_active:
            # Unknown address, wrong password and non-staff account all count the same, so neither the count nor
            # the lockout tells an admin address from any other.
            login_guard.record_failure(email)
            form.add_error(None, "Invalid email or password.")
            return render_admin_login(request, step="password", form=form)

        return _finish_password_login(request, member, email, "Admin login via password: %s")

    def _handle_remembered_password_step(self, request):
        import apps.authn.views.admin.login as login_api

        form = login_api.AdminRememberedPasswordForm(request.POST)
        if not form.is_valid():
            return render_admin_login(request, step="password", form=form)

        member = get_last_admin_login_member(request)
        if member is None:
            return render_admin_login(
                request,
                step="password",
                form=login_api.AdminPasswordForm(),
                error="Please enter your email to continue.",
            )

        guard_key = remembered_admin_guard_key(member)
        if login_guard.retry_after(guard_key):
            return _render_locked(request, form)

        if not member.check_password(form.cleaned_data["password"]):
            login_guard.record_failure(guard_key)
            form.add_error(None, "Invalid password.")
            return render_admin_login(request, step="password", form=form)

        return _finish_password_login(
            request,
            member,
            guard_key,
            "Admin login via remembered password: %s",
        )


def _render_locked(request, form):
    form.add_error(None, LOCKED_ERROR)
    return render_admin_login(request, step="password", form=form)


def _finish_password_login(request, member, guard_key, log_message):
    """Sign ``member`` in and clear ``guard_key``: the counter of the form that was used, and only that one."""
    login_guard.clear(guard_key)
    auth.login(request, member, backend="apps.authn.security.backends.EmailAuthBackend")
    clear_admin_login_session(request)
    logger.info(log_message, member.get_primary_email())
    response = redirect(safe_admin_next(request))
    return set_last_admin_login_cookie(response, member)
