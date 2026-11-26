"""Who may use the admin: the single access predicate.

There are two kinds of account: **Admins** and regular members. An Admin is an authenticated, active member with
``is_staff`` set, and every Admin has the same, complete set of permissions: every model in every app, in the Django
admin, through the shared ``safe_orm`` layer (the AI assistant) and through ``/admin-api/`` (the CLI). There are no
per-app grants and no higher tier. ``is_superuser`` is kept only as a mirror of ``is_staff`` (``Member.save()``) for
Django's own machinery; project code never authorises on it.

The helpers deliberately *duck-type* the user object — they only read attributes and never import ``Member`` — so
``apps.core`` keeps no import dependency on ``apps.authn``.
"""


def user_is_admin(user) -> bool:
    """Return whether ``user`` is an Admin: authenticated, active and staff."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "is_staff", False)
    )


def user_can_access_app(user, app_label: str) -> bool:
    """Return whether ``user`` may manage records in the Django app ``app_label``.

    Every Admin may manage every app, so this is ``user_is_admin``; the app label is kept in the signature because
    the admin base classes, the sidebar and the CLI ask per app.
    """
    return user_is_admin(user)
