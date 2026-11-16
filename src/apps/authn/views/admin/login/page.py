"""The admin sign-in page: rendering it, with any earlier code send that is still unresolved."""

import uuid

from django.contrib import admin
from django.shortcuts import render

from .state import (
    _SESSION_EMAIL,
    _SESSION_HIDE_EMAIL,
    get_admin_login_member,
    get_admin_member_display_name,
    get_last_admin_login_summary,
)


def get_unresolved_admin_send(request):
    request_id = request.session.get("admin_send_unresolved_request_id")
    if not request_id:
        return None
    from apps.authn.models import SendVerificationRequest
    from apps.authn.services.send_verification.guard import lookup_request
    from apps.authn.services.send_verification.rules.exceptions import SendVerificationError

    try:
        record = lookup_request(request, uuid.UUID(str(request_id)))
    except (ValueError, SendVerificationError):
        request.session.pop("admin_send_unresolved_request_id", None)
        return None
    if record.status in {
        SendVerificationRequest.Status.PROVIDER_ACCEPTED,
        SendVerificationRequest.Status.DEFINITELY_FAILED,
    }:
        request.session.pop("admin_send_unresolved_request_id", None)
        return None
    return record


def render_admin_login(request, *, form, step: str, email: str = "", **extra):
    from apps.authn.services.send_verification.proofs.principal import principal_from_request
    from apps.authn.services.send_verification.rules.constants import OP_ADMIN_LOGIN_REQUEST_CODE

    unresolved = get_unresolved_admin_send(request)
    if unresolved is not None:
        if step != "code":
            from apps.authn.views.admin.login import AdminCodeForm

            form = AdminCodeForm()
        step = "code"
        email = request.session.get(_SESSION_EMAIL, email)
        extra["message"] = "The previous send request is still unresolved. You can enter a code if it arrives."
        extra["send_verification_unresolved_request_id"] = str(unresolved.request_id)
        extra["send_verification_unresolved_challenge_id"] = unresolved.otp_challenge_id
    next_param = request.GET.get("next", "")
    next_qs = f"&next={next_param}" if next_param else ""
    use_different_account = request.GET.get("different") == "1"
    hide_email = request.session.get(_SESSION_HIDE_EMAIL, False)
    code_recipient_name = ""
    if step == "code" and hide_email:
        member = get_admin_login_member(request)
        if member is not None:
            code_recipient_name = get_admin_member_display_name(member)

    context = admin.site.each_context(request)
    context.update(
        {
            "site_title": admin.site.site_title,
            "site_header": admin.site.site_header,
            "title": "Log in",
            "password_mode_url": f"?mode=password{next_qs}",
            "email_code_mode_url": f"?step=email{next_qs}",
            "different_email_url": f"?step=email&different=1{next_qs}",
            "step": step,
            "form": form,
            "email": email,
            "hide_email": hide_email,
            "code_recipient_name": code_recipient_name,
            "send_verification_session_key": principal_from_request(request, operation=OP_ADMIN_LOGIN_REQUEST_CODE)[1],
            "last_admin_user": (
                get_last_admin_login_summary(request) if step != "code" and not use_different_account else None
            ),
        }
    )
    context.update(extra)
    return render(request, "admin/login.html", context)
