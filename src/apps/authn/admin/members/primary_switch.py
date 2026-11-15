"""Members → a member → **Switch primary email**, and "Make primary…" on a verified row of the member's Contact Emails.

GET shows a page that changes nothing: the member's addresses and, for the chosen verified address, every type that
changes, what the switch means for signing in, and the newsletter warnings (a switch never changes a subscription).
The POST applies it with ``switch_primary_email``: one transaction under the member lock, only a verified address,
refused when anything changed after the page was shown, and a typed word while ``ADMIN_REQUIRE_CONFIRMATION`` is on.
It is recorded, in that same transaction, in the History of the member and of each address whose type changed, and
the admin returns to the member page.

Who: the Members (authn) app and ``user_can_manage_member``, so a staff or superuser account needs the I2G Master (or
its own holder). Unfold wraps a detail-action URL only in ``admin_view`` (any staff, with Django's CSRF check), so the
view checks both itself; the button and the row links are left out for anyone else.
"""

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.utils import quote, unquote
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from unfold.decorators import action

from apps.core.utils.access import user_can_manage_member

from ...services.contacts.primary_switch import (
    PRIMARY,
    StaleSwitch,
    SwitchRefused,
    current_primary,
    fingerprint,
    member_emails,
    plan_primary_switch,
    switch_primary_email,
)
from .primary_switch_notes import outcome_messages, row_reason, switch_notes, why_not

ACTION = "switch_primary_email"
URL_NAME = "admin:authn_member_switch_primary_email"
TEMPLATE = "admin/authn/member/switch_primary.html"
CONFIRM_WORD = "switch"
VIA = "Switch primary email on the member page"
VIA_CONTACT_EMAILS = "Make selected email primary in Contact Emails"
PRIVILEGED = "Only an I2G Master may change the primary email of a staff or superuser account."
TYPE_LABELS = {"primary": "Primary", "secondary": "Secondary", "other": "Other"}


def confirmation_required() -> bool:
    return bool(getattr(settings, "ADMIN_REQUIRE_CONFIRMATION", True))


def switch_url(member_pk, contact_pk=None) -> str:
    url = reverse(URL_NAME, args=[quote(member_pk)])
    return f"{url}?{urlencode({'to': contact_pk})}" if contact_pk is not None else url


def is_candidate(email) -> bool:
    """Only a verified address that is not already the primary can become the primary."""
    return email.email_type != PRIMARY and email.verified


def primary_switch_cell(contact, *, enabled: bool):
    """The "Primary email" column of the member page's Contact Emails rows."""
    if contact is None or contact._state.adding or contact.member_id is None:
        return ""
    if contact.email_type == PRIMARY:
        return "Current primary"
    if not contact.verified:
        return format_html(
            '<span title="{}">Verify first</span>', "Only a verified address can become the primary email."
        )
    if not enabled:
        return "-"
    return format_html(
        '<a href="{}" class="text-primary-600 dark:text-primary-500 underline" title="{}">Make primary…</a>',
        switch_url(contact.member_id, contact.pk),
        "Opens a confirmation page; nothing changes until you confirm there. Save other edits on this page first.",
    )


def _rows(member, emails, target) -> list[dict]:
    after = {change.contact.pk: change.after for change in plan_primary_switch(emails, target)} if target else {}
    return [
        {
            "email": email,
            "type": TYPE_LABELS.get(email.email_type, email.email_type),
            "after": TYPE_LABELS.get(after[email.pk], after[email.pk]) if email.pk in after else "",
            "is_target": target is not None and email.pk == target.pk,
            "choose_url": switch_url(member.pk, email.pk) if is_candidate(email) else "",
            "reason": "" if is_candidate(email) else row_reason(email),
        }
        for email in emails
    ]


class PrimarySwitchAdminMixin:
    """``MemberAdmin``: the **Switch primary email** detail action and its page."""

    actions_detail = [ACTION]

    def may_switch_primary(self, request, member) -> bool:
        return (
            member is not None
            and self.has_change_permission(request, member)
            and user_can_manage_member(request.user, member)
        )

    def _button_owner(self, request, object_id):
        """The member page's member, with only the fields the permission check reads.

        ``get_object`` would load the whole row again (the multi-megabyte ``profile_image`` included) and prefetch
        every contact, on every member page, just to decide whether to show the button.
        """
        queryset = self.get_queryset(request).prefetch_related(None).only("id", "is_staff", "is_superuser")
        try:
            return queryset.filter(pk=unquote(str(object_id))).first()
        except (ValidationError, ValueError):
            return None

    def get_actions_detail(self, request, object_id):
        actions = super().get_actions_detail(request, object_id)
        member = self._button_owner(request, object_id) if object_id else None
        if self.may_switch_primary(request, member):
            return actions
        return [item for item in actions if not item.action_name.endswith(f"_{ACTION}")]

    @action(description="Switch primary email", url_path="switch-primary", icon="swap_horiz")
    def switch_primary_email(self, request, object_id):
        # The app check comes first, as in Django's change view: without the Members app, an unknown and a known
        # member both answer 403.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to change members.")
        member = self.get_object(request, unquote(str(object_id)))
        if member is None:
            raise Http404("No member matches the given query.")
        if not self.may_switch_primary(request, member):  # the same rule that shows the button
            raise PermissionDenied(PRIVILEGED)
        if request.method == "POST":
            return self._apply_primary_switch(request, member)
        return self._primary_switch_page(request, member, str(request.GET.get("to") or ""))

    def _primary_switch_page(self, request, member, target_id: str, *, status: int = 200):
        emails = member_emails(member)
        candidates = [email for email in emails if is_candidate(email)]
        target = next((email for email in candidates if str(email.pk) == target_id), None)
        if target_id and target is None:
            chosen = next((email for email in emails if str(email.pk) == target_id), None)
            messages.error(request, why_not(chosen) if chosen is not None else "That address is not this member's.")
        if not target_id and len(candidates) == 1:
            target = candidates[0]
        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": f"Switch primary email: {member}",
            "member": member,
            "rows": _rows(member, emails, target),
            "candidates": candidates,
            "target": target,
            "previous": current_primary(emails),
            "notes": switch_notes(request, member, emails, target) if target is not None else None,
            "fingerprint": fingerprint(member, emails),
            "confirm_word": CONFIRM_WORD if confirmation_required() else "",
            "change_url": reverse("admin:authn_member_change", args=[quote(member.pk)]),
            "page_url": switch_url(member.pk),
        }
        return TemplateResponse(request, TEMPLATE, context, status=status)

    def _apply_primary_switch(self, request, member):
        target_id = str(request.POST.get("to") or "")
        typed = str(request.POST.get("confirm") or "").strip().lower()
        if confirmation_required() and typed != CONFIRM_WORD:
            messages.error(request, f"Type “{CONFIRM_WORD}” to confirm. Nothing was changed.")
            return self._primary_switch_page(request, member, target_id, status=400)
        try:
            result = switch_primary_email(
                member=member,
                contact_email_id=target_id,
                seen=str(request.POST.get("fingerprint") or ""),
                actor=request.user,
                via=VIA,
            )
        except StaleSwitch as exc:
            messages.warning(request, str(exc))
            return self._primary_switch_page(request, member, target_id, status=409)
        except SwitchRefused as exc:
            messages.error(request, str(exc))
            return self._primary_switch_page(request, member, "", status=400)
        for level, text in outcome_messages(result):
            messages.add_message(request, level, text)
        return HttpResponseRedirect(reverse("admin:authn_member_change", args=[quote(member.pk)]))
