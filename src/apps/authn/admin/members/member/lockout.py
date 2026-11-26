"""The lockout rules on the Member admin: nobody removes their own Admin account, and the last active Admin stays.

Every Admin may edit, deactivate, demote or delete any member, other Admins included; ``admin_removal_refusal`` only
refuses the two removals that could lock the site out. Where they apply here:

- your own change page shows **Admin** and **Account active** read-only (with a note), and the change form refuses
  unticking either when it would break a rule (``MemberChangeForm``, given the acting member by ``get_form``);
- the delete page refuses with a message, and ``delete_model`` / ``delete_queryset`` re-check inside the transaction;
- "Delete selected members" checks the whole selection before its confirmation page (the bulk deactivate action does
  the same in ``helpers.deactivate_members``).
"""

from urllib.parse import unquote

from django.contrib import messages
from django.contrib.admin.actions import delete_selected
from django.contrib.admin.utils import quote
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse

from ....services.members.admins import DELETE, admin_removal_refusal

OWN_ACCOUNT_FIELDS = ("is_staff", "is_active")
OWN_ACCOUNT_NOTE = (
    "This is your own account. Admin and Account active are read-only here: you cannot remove your own Admin access. "
    "Another Admin can change them."
)


def admins_in(queryset):
    """The active Admins of a member selection, loaded light (the rules read nothing else; a selection can be large)."""
    return queryset.filter(is_staff=True, is_active=True).prefetch_related(None).only("id", "is_staff", "is_active")


def delete_selected_members(modeladmin, request, queryset):
    """Django's "Delete selected" action, refused as a whole when the selection breaks a lockout rule."""
    refusal = admin_removal_refusal(request.user, admins_in(queryset), action=DELETE)
    if refusal:
        modeladmin.message_user(request, f"{refusal} Nothing was deleted.", level=messages.ERROR)
        return None
    return delete_selected(modeladmin, request, queryset)


class MemberAdminLockoutMixin:
    """``MemberAdmin``: the lockout rules on the change form, the delete page and the bulk delete."""

    @staticmethod
    def is_own_account(request, obj) -> bool:
        return obj is not None and obj.pk is not None and obj.pk == getattr(request.user, "pk", None)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if self.is_own_account(request, obj):
            readonly.extend(field for field in OWN_ACCOUNT_FIELDS if field not in readonly)
        return readonly

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            return form
        # The form checks the lockout rules on its own fields, so it needs the member who submits it.
        return type(form.__name__, (form,), {"removal_actor": request.user})

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            _func, name, description = actions["delete_selected"]
            actions["delete_selected"] = (delete_selected_members, name, description)
        return actions

    def delete_view(self, request, object_id, extra_context=None):
        member = self.get_object(request, unquote(str(object_id)))
        refusal = admin_removal_refusal(request.user, [member], action=DELETE) if member is not None else ""
        if refusal:
            self.message_user(request, f"{refusal} Nothing was deleted.", level=messages.ERROR)
            return HttpResponseRedirect(reverse("admin:authn_member_change", args=[quote(member.pk)]))
        return super().delete_view(request, object_id, extra_context)

    def delete_model(self, request, obj):
        with transaction.atomic():
            refusal = admin_removal_refusal(request.user, [obj], action=DELETE)
            if refusal:
                raise PermissionDenied(refusal)
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            refusal = admin_removal_refusal(request.user, admins_in(queryset), action=DELETE)
            if refusal:
                raise PermissionDenied(refusal)
            super().delete_queryset(request, queryset)
