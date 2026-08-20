"""Owner-aware authorization for the contact-record admins.

``BaseModelAdmin`` grants access per Django app and ignores the object, so any staff member holding the
``authn`` grant could operate on contact rows belonging to a staff or superuser account. That is a
privilege-escalation path, not just an untidy permission: a verified ``ContactEmail`` attached to a
privileged member is a working admin-login factor, and a ``ContactPhone`` is an SMS recovery factor.
Layer ``user_can_manage_member`` on top so only an I2G Master (or the account's owner) can touch them.
"""

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

from apps.core.utils.access import user_can_manage_member

PRIVILEGED_OWNER_ERROR = _(
    "Only an I2G Master may add or change contact records for a staff or superuser account, "
    "because a verified contact is a working sign-in factor for that account."
)


class PrivilegedOwnerAdminMixin:
    """Restrict writes to contact rows whose ``member`` is a staff/superuser account.

    Enforced at three layers because they cover different request paths:
    ``formfield_for_foreignkey`` gives a clean validation error on the add/change form,
    ``has_*_permission`` hides the change/delete affordances, and ``save_model``/``delete_model`` are
    the authoritative backstop that also covers ``list_editable`` and forged POSTs.
    """

    # Fields a non-superuser must not set on a privileged account's contact row.
    owner_protected_fields = ("verified",)

    @staticmethod
    def _can_manage(request, member) -> bool:
        return user_can_manage_member(request.user, member)

    def _assert_can_manage(self, request, member):
        if not self._can_manage(request, member):
            raise PermissionDenied(str(PRIVILEGED_OWNER_ERROR))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "member" and not request.user.is_superuser:
            # Django validates the submitted value against this queryset, so a non-superuser gets a
            # normal "not one of the available choices" error rather than a bare 403.
            queryset = kwargs.get("queryset") or db_field.remote_field.model._default_manager.all()
            kwargs["queryset"] = queryset.exclude(is_staff=True).exclude(is_superuser=True) | queryset.filter(
                pk=request.user.pk
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        if obj is not None and not self._can_manage(request, obj.member):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and not self._can_manage(request, obj.member):
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and not self._can_manage(request, obj.member):
            for field in self.owner_protected_fields:
                if field not in readonly:
                    readonly.append(field)
        return readonly

    def save_model(self, request, obj, form, change):
        # Check the submitted owner and, on a change, the owner the row currently has — otherwise a
        # row could be moved off a privileged account and back, or edited before being re-pointed.
        self._assert_can_manage(request, obj.member)
        if change and obj.pk:
            current = type(obj)._default_manager.filter(pk=obj.pk).select_related("member").first()
            if current is not None:
                self._assert_can_manage(request, current.member)
        return super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        self._assert_can_manage(request, obj.member)
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset.select_related("member"):
            self._assert_can_manage(request, obj.member)
        return super().delete_queryset(request, queryset)

    def manageable(self, request, queryset):
        """Narrow ``queryset`` to rows the requester may write, for use by bulk actions."""
        if request.user.is_superuser:
            return queryset, 0
        protected = [obj.pk for obj in queryset.select_related("member") if not self._can_manage(request, obj.member)]
        if not protected:
            return queryset, 0
        return queryset.exclude(pk__in=protected), len(protected)
