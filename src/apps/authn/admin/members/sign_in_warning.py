"""Warn, never block, when an admin change leaves a member with no verified email address or phone number.

Unticking **Verified** stops sign-in with that address or number, and stops no mail. When it was the member's last
verified email or phone, they cannot sign in with a code or a password until one is verified again (codes and
passwords work with any verified address, or a verified phone); only a personal sign-in link from an email they already
received (``LoginLinkToken``, checked for an active account and expiry only) still works. Without one they cannot
reach their account page to verify an address either, so the warning says how staff fix it. The member API refuses to
delete that last contact; the admin allows unverifying it (the address may never have been theirs) and says so:

- ``lost_sign_in`` wraps a write (a save, a bulk "mark unverified", a delete) and warns about every member who had a
  verified contact before it and has none after;
- ``member_page_row`` and ``contact_row`` add the same warning to the type-to-confirm page, before the save.
"""

from contextlib import contextmanager

from django.contrib import messages
from django.contrib.auth import get_user_model

from ...models import ContactEmail, ContactPhone
from ...services.account.recovery import count_verified_recovery_contacts, members_with_sign_in_contact

MAX_NAMED = 5
ROW = {
    "field": "sign-in-warning",
    "label": "Warning: signing in",
    "old_value": "The member has a verified email or phone, so they can sign in",
    "new_value": (
        "No verified email or phone left: the member cannot sign in with a code or a password until one is verified "
        "(mail still goes)"
    ),
}


def _names(member_ids) -> str:
    members = get_user_model().objects.filter(pk__in=member_ids).prefetch_related("contact_emails")
    names = sorted(str(member) for member in members)
    shown = ", ".join(names[:MAX_NAMED])
    return f"{shown} and {len(names) - MAX_NAMED} more" if len(names) > MAX_NAMED else shown


def warning_text(member_ids) -> str:
    count = len(member_ids)
    subject = f"{_names(member_ids)} now has" if count == 1 else f"{count} members now have"
    detail = "" if count == 1 else f" ({_names(member_ids)})"
    return (
        f"{subject} no verified email address or phone number{detail}, so they cannot sign in with a code or a "
        "password until one is verified (only a personal sign-in link from an email they received still works, until "
        "it expires). Mail to their addresses still goes. If that was not intended, tick Verified again on an email "
        "address that is theirs, or verify their phone with “Verify by SMS code”."
    )


@contextmanager
def lost_sign_in(request, member_ids):
    """Run the write inside the ``with``; afterwards, warn about members it left with no verified contact."""
    before = members_with_sign_in_contact(member_ids)
    yield
    lost = before - members_with_sign_in_contact(before)
    if lost:
        messages.warning(request, warning_text(lost))


def _verified_after(formset) -> int:
    """How many of the formset's rows stay (or become) verified once it is saved."""
    count = 0
    for form in formset.forms:
        data = getattr(form, "cleaned_data", None) or {}
        if data.get("DELETE") or (form.instance._state.adding and not form.has_changed()):
            continue
        if data.get("verified", form.instance.verified):
            count += 1
    return count


def member_page_row(member, formsets) -> dict | None:
    """The confirmation-page warning when the member page's contact rows, saved, leave no verified contact."""
    # One id in, so any result means "has one" (the confirmation flow can hand over the pk as a string, while the
    # result holds the database's UUIDs).
    if member is None or not members_with_sign_in_contact([member.pk]):
        return None
    remaining = 0
    for model in (ContactEmail, ContactPhone):
        formset = next((item for item in formsets if getattr(item, "model", None) is model), None)
        if formset is None:
            remaining += model.objects.filter(member=member, verified=True).count()
        else:
            remaining += _verified_after(formset)
    return None if remaining else dict(ROW)


def contact_row(current, form) -> dict | None:
    """The confirmation-page warning when saving one contact row (``current``: as stored) leaves its member with no
    verified contact: it is unticked, or moved to another member."""
    member = current.member if current is not None else None
    if member is None:
        return None
    exclude = (
        {"exclude_email_pk": current.pk} if isinstance(current, ContactEmail) else {"exclude_phone_pk": current.pk}
    )
    if not current.verified or count_verified_recovery_contacts(member, **exclude):
        return None
    data = form.cleaned_data
    stays = data.get("member", member) == member and data.get("verified", current.verified)
    return None if stays else dict(ROW)


class SignInWarningAdminMixin:
    """Contact Emails and Contact Phones: warn when a save (the change form or the list's editable columns), or a
    delete, leaves a member with no verified email or phone, and say so on the confirmation page before a save."""

    def get_confirmation_diff(self, request, obj, form, formsets, action_type):
        diff = super().get_confirmation_diff(request, obj, form, formsets, action_type)
        if action_type != "change" or not diff:
            return diff
        # ``obj`` already holds the submitted values: compare with the row as stored.
        current = type(obj)._default_manager.filter(pk=obj.pk).select_related("member").first()
        warning = contact_row(current, form)
        return [*diff, warning] if warning else diff

    def save_model(self, request, obj, form, change):
        owners = {obj.member_id}
        if change:
            owners.update(type(obj)._default_manager.filter(pk=obj.pk).values_list("member_id", flat=True))
        with lost_sign_in(request, owners):
            return super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        with lost_sign_in(request, [obj.member_id]):
            return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with lost_sign_in(request, set(queryset.values_list("member_id", flat=True))):
            return super().delete_queryset(request, queryset)
