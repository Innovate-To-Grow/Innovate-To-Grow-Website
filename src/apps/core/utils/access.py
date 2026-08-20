"""Per-Django-app admin access predicate.

The project replaced per-user Django ``user_permissions`` with coarse per-app access:
an admin member carries a list of app labels (``Member.admin_apps``) and may
view/add/change/delete every model in any app on that list. ``is_superuser`` (the
I2G Master account) bypasses the list entirely.

This helper is the single source of truth for that decision and is enforced at every
gate (the Django admin base class, the shared ``safe_orm`` layer / AI action engine,
and the ``/admin-api/`` CLI). It deliberately *duck-types* the user object — it only
reads attributes and never imports ``Member`` — so ``apps.core`` keeps no import
dependency on ``apps.authn``.
"""


def user_can_access_app(user, app_label: str) -> bool:
    """Return whether ``user`` may manage records in the Django app ``app_label``.

    Access requires an authenticated, active staff member. Superusers (I2G Master)
    are always granted. Everyone else is granted only for the apps listed in their
    ``admin_apps``.
    """
    if not (
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "is_staff", False)
    ):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return app_label in (getattr(user, "admin_apps", None) or [])


def user_can_manage_member(user, target) -> bool:
    """Return whether ``user`` may act on ``target``'s privileged account state.

    ``user_can_access_app`` is deliberately object-independent, which means every admin holding the
    ``authn`` grant would otherwise be able to reset the I2G Master's password, attach a login factor
    to their account, or deactivate them. Layer this on top wherever an admin write targets a specific
    member: superusers may do anything, anyone may manage their own account, and otherwise the target
    must not itself be staff or a superuser.

    Duck-typed like ``user_can_access_app`` so ``apps.core`` keeps no dependency on ``apps.authn``.
    """
    if getattr(user, "is_superuser", False):
        return True
    if target is None:
        return False
    target_pk = getattr(target, "pk", None)
    if target_pk is not None and target_pk == getattr(user, "pk", None):
        return True
    return not (getattr(target, "is_staff", False) or getattr(target, "is_superuser", False))
