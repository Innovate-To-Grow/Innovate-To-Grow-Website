"""Who may act on a privileged (staff or superuser) member: superuser-only fields, password resets and deletes."""

from urllib.parse import unquote

from django.core.exceptions import PermissionDenied

from apps.core.utils.access import user_can_manage_member


class MemberAdminProtectionMixin:
    # Granting admin-app access or staff status is an I2G Master (superuser)
    # responsibility. A non-superuser admin must not be able to widen their own
    # (or anyone's) privileges by editing these fields, so they are read-only for
    # non-superusers — Django drops any submitted value for read-only fields, so
    # this is enforced server-side, not just hidden in the rendered form.
    superuser_only_fields = ("is_staff", "admin_apps")

    @staticmethod
    def can_manage_target(request, target) -> bool:
        """Whether ``request.user`` may act on the privileged parts of ``target``'s account."""
        return user_can_manage_member(request.user, target)

    def user_change_password(self, request, id, form_url=""):  # noqa: A002 - UserAdmin's signature
        """Refuse password resets on privileged accounts unless the actor is a superuser.

        ``UserAdmin``'s inherited ``<id>/password/`` route is gated only by ``has_change_permission``,
        which here is the object-independent authn-app predicate — so any staffer with that grant could
        set the superuser's password and log in as them, defeating ``superuser_only_fields``.
        """
        target = self.get_object(request, unquote(str(id)))
        if not self.can_manage_target(request, target):
            raise PermissionDenied("Only an I2G Master may change a privileged account's password.")
        return super().user_change_password(request, id, form_url=form_url)

    def has_delete_permission(self, request, obj=None):
        # Deleting a privileged account is itself a privileged operation — same scope as
        # ``protected_target_fields``. The object-level check covers the delete view (and hides its
        # button); the bulk path is backstopped in ``delete_queryset`` below.
        if obj is not None and not self.can_manage_target(request, obj):
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        # ``delete_selected`` is gated only by the object-independent ``has_delete_permission``,
        # so re-apply the per-object guard before anything is removed.
        for member in queryset:
            if not self.can_manage_target(request, member):
                raise PermissionDenied("Only an I2G Master may delete a staff or superuser account.")
        return super().delete_queryset(request, queryset)

    # Editable on an ordinary member, but not on a staff/superuser account unless the actor is an
    # I2G Master — deactivating or renaming a privileged account is itself a privileged operation.
    protected_target_fields = ("is_active",)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return readonly
        locked = list(self.superuser_only_fields)
        if obj is not None and not self.can_manage_target(request, obj):
            locked.extend(self.protected_target_fields)
        readonly.extend(field for field in dict.fromkeys(locked) if field not in readonly)
        return readonly
