"""The Contact Emails change list's bulk actions: make primary, mark (un)verified, toggle the subscription."""

from django.contrib import admin, messages

from apps.authn.services.contacts.primary_switch import SwitchRefused, switch_primary_email

from ..primary_switch.notes import outcome_messages
from ..primary_switch.switch import VIA_CONTACT_EMAILS
from ..shared.sign_in_warning import lost_sign_in


class ContactEmailActionsMixin:
    @admin.action(description="Make selected email primary")
    def make_primary(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly one email to make primary.",
                level=messages.ERROR,
            )
            return

        contact_email = queryset.select_related("member").first()
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

    @admin.action(description="Mark selected emails as verified")
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified=True)
        self.message_user(request, f"{updated} email(s) marked as verified.")

    @admin.action(description="Mark selected emails as unverified (stops sign-in with them, not mail)")
    def mark_unverified(self, request, queryset):
        with lost_sign_in(request, set(queryset.values_list("member_id", flat=True))):
            updated = queryset.update(verified=False)
        self.message_user(request, f"{updated} email(s) marked as unverified.")

    @admin.action(description="Toggle subscription status")
    def toggle_subscribe(self, request, queryset):
        count = 0
        for email in queryset:
            email.subscribe = not email.subscribe
            email.save()
            count += 1
        self.message_user(request, f"Toggled subscription for {count} email(s).")
