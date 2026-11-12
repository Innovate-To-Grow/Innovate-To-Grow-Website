"""Phone verification in the admin: who may set ``ContactPhone.verified``, how it is shown, and the staff SMS-code check.

A verified number is a sign-in factor: whoever holds it can sign in to its account with a texted code. So a number
becomes verified only by proving possession with a one-time code, never by a tick:

* the member, from the account page (``/authn/contact-phones/<id>/request-verification/``), or at signup;
* staff, with **Verify by SMS code** (``StaffPhoneCodeMixin``): send a code to the number, ask the member for it
  (in person, or on a call to them), enter it. A code that went to a mistyped or recycled number never comes back.

Staff can still switch verification off (untick, or "Mark selected phones as unverified"), and a number whose digits
are changed here, or that is moved to another member, starts unverified again.
"""

from __future__ import annotations

import re

from django import forms
from django.contrib import messages
from django.contrib.admin.utils import quote, unquote
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils.html import format_html

from ....models import ContactPhone
from ....services.contacts.contact_phones import request_phone_verification, verify_phone_code
from ....services.email.challenges import AuthChallengeInvalid
from ....services.send_verification.config import load_settings
from ....services.send_verification.constants import KIND_PHONE, SMS_CHANNEL
from ....services.send_verification.exceptions import SendVerificationError
from ....services.send_verification.quotas import reserve_send_quotas
from ....services.sms import PhoneVerificationError, PhoneVerificationInvalid, PhoneVerificationThrottled

VERIFIED_HELP = (
    "Only a verified number can be used to sign in with a texted code. A number becomes verified only with an SMS "
    "code: from the member's account page, or with “Verify by SMS code” here. Untick to stop SMS sign-in."
)
VERIFY_URL_NAME = "authn_contactphone_verify_by_code"
_CODE = re.compile(r"\d{6}")


def _e164(phone_number: str, region: str) -> str:
    country_code = region.split("-")[0] if "-" in region else region
    return f"+{country_code}{ContactPhone._to_national_digits(phone_number, region)}"


class ContactPhoneAdminForm(forms.ModelForm):
    """``verified`` may be switched off here but never on (that takes a code), and changing the number, or the member it
    belongs to, unverifies it."""

    class Meta:
        model = ContactPhone
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get("verified")
        if field is not None:
            field.help_text = VERIFIED_HELP
            # Disabled: Django ignores whatever is posted for it and keeps the stored value (False).
            field.disabled = not self.instance.verified

    def clean(self):
        cleaned = super().clean()
        if "verified" in self.fields and (self._number_changed(cleaned) or self._member_changed(cleaned)):
            # A different number has proven nothing yet, and neither has the same number on another account: its
            # code proved that someone holds the phone, not that the new member does.
            cleaned["verified"] = False
        return cleaned

    def _member_changed(self, cleaned) -> bool:
        # The inline's member is its parent (unchanged); on the phone's own page staff may pick another member.
        if self.instance._state.adding or "member" not in cleaned:
            return False
        return getattr(cleaned["member"], "pk", None) != self.instance.member_id

    def _number_changed(self, cleaned) -> bool:
        if self.instance._state.adding or not self.instance.phone_number:
            return False
        number = cleaned.get("phone_number", self.instance.phone_number) or ""
        region = cleaned.get("region", self.instance.region) or self.instance.region
        return _e164(number, region) != _e164(self.instance.phone_number, self.instance.region)


def verify_url(contact) -> str:
    return reverse(f"admin:{VERIFY_URL_NAME}", args=[quote(contact.pk)])


def sms_sign_in_status(contact, *, with_link: bool = True) -> str:
    """A badge saying whether ``contact`` can sign in by SMS, with the staff verification link when it cannot."""
    # A new inline row is not saved yet (its UUID pk is set on construction, so check ``_state``): nothing to show.
    if contact is None or contact._state.adding:
        return "-"
    if contact.verified:
        return render_to_string("unfold/helpers/label.html", {"text": "Verified · SMS sign-in on", "type": "success"})
    badge = render_to_string("unfold/helpers/label.html", {"text": "Unverified · no SMS sign-in", "type": "warning"})
    if not with_link or contact.member_id is None:
        return format_html("{}", badge)
    return format_html(
        '{} <a class="text-primary-600 underline" href="{}">Verify by SMS code</a>', badge, verify_url(contact)
    )


class StaffPhoneCodeMixin:
    """The **Verify by SMS code** page of the Contact Phone admin (see the module docstring)."""

    def verify_by_code_urls(self):
        return [
            path(
                "<path:object_id>/verify-by-code/",
                self.admin_site.admin_view(self.verify_by_code_view),
                name=VERIFY_URL_NAME,
            )
        ]

    def verify_by_code_view(self, request, object_id):
        contact = self.get_object(request, unquote(object_id))
        if contact is None:
            raise Http404("Contact phone not found.")
        # ``admin_view`` only checks is_staff: this is the app grant plus the privileged-account guard.
        if not self.has_change_permission(request, contact):
            raise PermissionDenied
        change_url = reverse("admin:authn_contactphone_change", args=[quote(contact.pk)])
        if contact.member_id is None:
            messages.error(request, "This number belongs to no member, so there is no account to verify it for.")
            return redirect(change_url)
        if request.method == "POST":
            if request.POST.get("action") == "send":
                self._send_staff_code(request, contact)
            elif request.POST.get("action") == "verify" and self._check_staff_code(request, contact):
                return redirect(change_url)
            return redirect(verify_url(contact))
        context = {
            **self.admin_site.each_context(request),
            "title": "Verify by SMS code",
            "contact": contact,
            "status": sms_sign_in_status(contact, with_link=False),
            "change_url": change_url,
            "opts": self.model._meta,
        }
        return render(request, "admin/authn/contactphone/verify_by_code.html", context)

    def _send_staff_code(self, request, contact) -> None:
        try:
            # The same per-number cooldown as every other code request (no double send on a double click).
            with transaction.atomic():
                reserve_send_quotas(
                    config=load_settings(),
                    channel=SMS_CHANNEL,
                    destination_kind=KIND_PHONE,
                    destination_normalized=contact.to_e164(),
                )
            request_phone_verification(member=contact.member, contact_phone_id=contact.pk)
        except AuthChallengeInvalid as exc:
            messages.error(request, str(exc))
        except SendVerificationError as exc:
            messages.error(request, f"The code was not sent: {exc.detail}")
        except PhoneVerificationError as exc:
            messages.error(request, f"The code was not sent: {exc}")
        else:
            self.log_change(request, contact, "Sent an SMS verification code (staff check).")
            messages.success(
                request,
                f"Code sent to {contact.get_formatted_number()}. Ask the member to read it to you, then enter it below.",
            )

    def _check_staff_code(self, request, contact) -> bool:
        code = (request.POST.get("code") or "").strip()
        if not _CODE.fullmatch(code):
            messages.error(request, "Enter the 6-digit code the member read to you.")
            return False
        try:
            verify_phone_code(member=contact.member, contact_phone_id=contact.pk, code=code)
        except PhoneVerificationThrottled:
            messages.error(request, "Too many wrong codes. Send a new code.")
            return False
        except (PhoneVerificationInvalid, AuthChallengeInvalid):
            messages.error(request, "That code is wrong or has expired. Check it with the member, or send a new one.")
            return False
        self.log_change(request, contact, "Verified with an SMS code the member read back to staff.")
        messages.success(request, "Verified. This number can now be used to sign in with a texted code.")
        return True
