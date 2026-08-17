from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.authn.services.contacts.contact_emails import make_contact_email_primary
from apps.authn.services.email.challenges import AuthChallengeInvalid
from apps.core.admin import BaseModelAdmin

from ....models import ContactEmail, Member
from .guards import PrivilegedOwnerAdminMixin

PRIMARY_EMAIL_EDIT_ERROR = _(
    "The current primary email's owner, address, and type cannot be edited directly. "
    "Make another verified email primary first."
)
PRIMARY_EMAIL_DELETE_ERROR = _(
    "The current primary email cannot be deleted directly. Make another email primary first."
)
PRIMARY_EMAIL_PROMOTION_ERROR = _(
    "A primary email cannot be assigned directly. Use the 'Make selected email primary' action."
)


def _primary_identity_changed(current, candidate) -> bool:
    """Return whether an update would rewrite the identity/type of a primary row."""
    return (
        current.member_id != candidate.member_id
        or current.email_address != candidate.email_address
        or current.email_type != candidate.email_type
    )


class ContactEmailAdminForm(forms.ModelForm):
    """Reject forged form submissions that bypass primary-email admin controls."""

    class Meta:
        model = ContactEmail
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk:
            return cleaned_data

        current = ContactEmail.objects.filter(pk=self.instance.pk).first()
        if current is None or current.member_id is None:
            # An unowned row has no sign-in address to protect; let an admin adopt or fix it.
            return cleaned_data

        requested_member = cleaned_data.get("member", current.member)
        requested_email = cleaned_data.get("email_address", current.email_address)
        requested_type = cleaned_data.get("email_type", current.email_type)

        if current.email_type == "primary" and (
            requested_member != current.member
            or requested_email != current.email_address
            or requested_type != current.email_type
        ):
            raise forms.ValidationError(PRIMARY_EMAIL_EDIT_ERROR)

        if current.email_type != "primary" and requested_type == "primary":
            raise forms.ValidationError(PRIMARY_EMAIL_PROMOTION_ERROR)

        return cleaned_data


@admin.register(ContactEmail)
class ContactEmailAdmin(PrivilegedOwnerAdminMixin, BaseModelAdmin):
    """Admin for ContactEmail model."""

    form = ContactEmailAdminForm
    list_display = (
        "email_address",
        "member",
        "email_type",
        "verified",
        "subscribe",
        "created_at",
    )
    list_filter = ("email_type", "verified", "subscribe", "created_at")
    search_fields = ("email_address", "member__first_name", "member__last_name")
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("verified", "subscribe")
    autocomplete_fields = ["member"]
    fieldsets = (
        (None, {"fields": ("member", "email_address", "email_type")}),
        (_("Status"), {"fields": ("verified", "subscribe")}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    actions = ["make_primary", "mark_verified", "mark_unverified", "toggle_subscribe"]

    @staticmethod
    def _is_owned_primary(obj) -> bool:
        """Whether ``obj`` is a primary email that actually belongs to a member.

        The protections below exist to keep a member's sign-in address stable, so they must not apply
        to an *unowned* row. ``member`` is nullable and ``email_type`` defaults to "primary", so a row
        saved with no owner became permanently unusable: every identity field frozen, delete refused,
        and ``make_primary`` bailing out because there is no member — while it kept squatting on a
        globally unique address.
        """
        return obj is not None and obj.member_id is not None and obj.email_type == "primary"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if self._is_owned_primary(obj):
            for field in ("member", "email_address", "email_type"):
                if field not in readonly:
                    readonly.append(field)
        return readonly

    def has_delete_permission(self, request, obj=None):
        if self._is_owned_primary(obj):
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)

        # The member row is the mutex shared with make_contact_email_primary().
        # Re-read after taking it so an admin save cannot race a primary swap.
        current = ContactEmail.objects.filter(pk=obj.pk).only("member_id").first()
        if current is None:
            return super().save_model(request, obj, form, change)

        with transaction.atomic():
            if current.member_id is not None:
                Member.objects.select_for_update().get(pk=current.member_id)
            current = ContactEmail.objects.select_for_update().get(pk=obj.pk)
            if current.member_id is None:
                return super().save_model(request, obj, form, change)
            if current.email_type == "primary" and _primary_identity_changed(current, obj):
                raise PermissionDenied(PRIMARY_EMAIL_EDIT_ERROR)
            if current.email_type != "primary" and obj.email_type == "primary":
                raise PermissionDenied(PRIMARY_EMAIL_PROMOTION_ERROR)
            return super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        with transaction.atomic():
            current = ContactEmail.objects.filter(pk=obj.pk).only("member_id").first()
            if current is None:
                return
            if current.member_id is not None:
                Member.objects.select_for_update().get(pk=current.member_id)
            current = ContactEmail.objects.select_for_update().get(pk=obj.pk)
            if current.member_id is not None and current.email_type == "primary":
                raise PermissionDenied(PRIMARY_EMAIL_DELETE_ERROR)
            super().delete_model(request, current)

    def delete_queryset(self, request, queryset):
        selected_ids = list(queryset.values_list("pk", flat=True))
        if not selected_ids:
            return

        with transaction.atomic():
            member_ids = sorted(
                {
                    member_id
                    for member_id in ContactEmail.objects.filter(pk__in=selected_ids).values_list(
                        "member_id", flat=True
                    )
                    if member_id is not None
                },
                key=str,
            )
            list(Member.objects.select_for_update().filter(pk__in=member_ids).order_by("pk"))
            locked = ContactEmail.objects.select_for_update().filter(pk__in=selected_ids)
            if locked.filter(email_type="primary", member__isnull=False).exists():
                raise PermissionDenied(PRIMARY_EMAIL_DELETE_ERROR)
            super().delete_queryset(request, locked)

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
            updated = make_contact_email_primary(
                member=contact_email.member,
                contact_email_id=contact_email.pk,
            )
        except AuthChallengeInvalid as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return

        self.message_user(
            request,
            f"{updated.email_address} is now the primary email.",
            level=messages.SUCCESS,
        )

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

    @admin.action(description="Mark selected emails as unverified")
    def mark_unverified(self, request, queryset):
        allowed, skipped = self.manageable(request, queryset)
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
