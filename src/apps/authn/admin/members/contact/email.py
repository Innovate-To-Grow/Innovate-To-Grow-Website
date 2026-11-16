from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.admin import BaseModelAdmin

from ....models import ContactEmail, Member
from ..shared.filters import EmailSubscribedFilter, EmailVerifiedFilter, MemberAccountFilter
from ..shared.search import RankedSearchMixin, contact_email_search_rank
from ..shared.sign_in_warning import SignInWarningAdminMixin
from .email_actions import ContactEmailActionsMixin
from .email_form import (
    PRIMARY_EMAIL_DELETE_ERROR,
    PRIMARY_EMAIL_EDIT_ERROR,
    PRIMARY_EMAIL_PROMOTION_ERROR,
    ContactEmailAdminForm,
    _primary_identity_changed,
)
from .guards import PrivilegedOwnerAdminMixin


@admin.register(ContactEmail)
class ContactEmailAdmin(
    ContactEmailActionsMixin, RankedSearchMixin, SignInWarningAdminMixin, PrivilegedOwnerAdminMixin, BaseModelAdmin
):
    """Admin for ContactEmail model.

    Verified and Subscribed belong to the address; **Account active** is its member's account flag, shown next to them
    so the two are not confused (an unlinked address has no account).
    """

    form = ContactEmailAdminForm
    list_display = (
        "email_address",
        "member",
        "email_type",
        "verified",
        "subscribe",
        "account_active",
        "created_at",
    )
    list_filter = (EmailVerifiedFilter, EmailSubscribedFilter, "email_type", MemberAccountFilter, "created_at")
    # ``member`` is nullable, so the changelist's automatic select_related() would not follow it.
    list_select_related = ("member",)
    search_fields = ("email_address", "member__first_name", "member__last_name")
    # The address equal to the search comes first, then addresses that start with it (``jdoe`` → ``jdoe@…``).
    search_rank = staticmethod(contact_email_search_rank)
    search_help_text = "Email address or member name"
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

    @admin.display(description="Account active", boolean=True, ordering="member__is_active")
    def account_active(self, obj):
        return None if obj.member_id is None else obj.member.is_active

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
            # ``of=("self",)``: the owner guard later reads these rows with ``select_related("member")``, a LEFT JOIN
            # (``member`` is nullable), and PostgreSQL refuses FOR UPDATE on the nullable side of an outer join. The
            # members are already locked just above.
            locked = ContactEmail.objects.select_for_update(of=("self",)).filter(pk__in=selected_ids)
            if locked.filter(email_type="primary", member__isnull=False).exists():
                raise PermissionDenied(PRIMARY_EMAIL_DELETE_ERROR)
            super().delete_queryset(request, locked)
