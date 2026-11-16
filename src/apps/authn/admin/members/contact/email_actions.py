"""The Contact Emails change list's bulk actions: make primary, mark (un)verified, toggle the subscription."""

from django.contrib import admin, messages

from apps.authn.services.contacts.primary_switch import SwitchRefused, switch_primary_email

from ..primary_switch.notes import outcome_messages
from ..primary_switch.switch import VIA_CONTACT_EMAILS
from ..shared.sign_in_warning import lost_sign_in


class ContactEmailActionsMixin:
    @admin.action(description="Make selected email primary")
    def make_primary(self, request, queryset):
        # Apply the owner guard like the sibling actions: the primary address is where a member's
        # admin login codes are sent, so swapping it is a write on the owner, not just the row.
        allowed, skipped = self.manageable(request, queryset)
        self._report_skipped(request, skipped)
        if allowed.count() != 1:
            self.message_user(
                request,
                "Select exactly one email to make primary.",
                level=messages.ERROR,
            )
            return

        contact_email = allowed.select_related("member").first()
        if contact_email is None or contact_email.member is None:
            self.message_user(
                request,
                "The selected email must belong to a member.",
                level=messages.ERROR,
            )
            return

        try:
            # Same service and history as the member page's "Switch primary email" (written in its transaction).
            result = switch_primary_email(
                member=contact_email.member,
                contact_email_id=contact_email.pk,
                actor=request.user,
                via=VIA_CONTACT_EMAILS,
            )
        except SwitchRefused as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return

        for level, text in outcome_messages(result):
            self.message_user(request, text, level=level)

    def _report_skipped(self, request, skipped):
        if skipped:
            self.message_user(
                request,
                f"{skipped} email(s) on staff or superuser accounts skipped — only an I2G Master may change those.",
                level=messages.WARNING,
            )

    @admin.action(description="Mark selected emails as verified")
    def mark_verified(self, request, queryset):
        # ``queryset.update`` bypasses save_model, so the owner guard has to be applied here too:
        # marking an email on a staff account verified turns it into an admin-login factor.
        allowed, skipped = self.manageable(request, queryset)
        updated = allowed.update(verified=True)
        self.message_user(request, f"{updated} email(s) marked as verified.")
        self._report_skipped(request, skipped)

    @admin.action(description="Mark selected emails as unverified (stops sign-in with them, not mail)")
    def mark_unverified(self, request, queryset):
        allowed, skipped = self.manageable(request, queryset)
        with lost_sign_in(request, set(allowed.values_list("member_id", flat=True))):
            updated = allowed.update(verified=False)
        self.message_user(request, f"{updated} email(s) marked as unverified.")
        self._report_skipped(request, skipped)

    @admin.action(description="Toggle subscription status")
    def toggle_subscribe(self, request, queryset):
        allowed, skipped = self.manageable(request, queryset)
        count = 0
        for email in allowed:
            email.subscribe = not email.subscribe
            email.save()
            count += 1
        self.message_user(request, f"Toggled subscription for {count} email(s).")
        self._report_skipped(request, skipped)
