from rest_framework.permissions import BasePermission

from apps.core.utils.access import user_is_admin


class IsActiveStaff(BasePermission):
    """Allow only Admins (authenticated, active staff members).

    There are no per-model Django permission checks on /admin-api/: every Admin
    may use every model, so being an Admin is the gate, backed by the shared hard
    denylist.
    """

    message = "An active Admin account is required."

    def has_permission(self, request, view):
        return user_is_admin(request.user)
