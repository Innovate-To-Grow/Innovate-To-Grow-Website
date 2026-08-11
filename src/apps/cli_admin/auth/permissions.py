from rest_framework.permissions import BasePermission


class IsActiveStaff(BasePermission):
    """Allow only authenticated, active staff members.

    There are no per-model Django permission checks on /admin-api/: staff status
    is the gate, backed by the shared hard denylist.
    """

    message = "Active staff status is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff)
