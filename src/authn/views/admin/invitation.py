"""
View for accepting admin invitations (plain Django, not DRF).
"""

from django.contrib import admin
from django.shortcuts import render
from django.views import View

from authn.forms.invitation import AcceptInvitationForm
from authn.models import ContactEmail
from authn.models.members.admin_invitation import AdminInvitation

Member = None  # resolved lazily


def _get_member_model():
    global Member
    if Member is None:
        from django.contrib.auth import get_user_model

        Member = get_user_model()
    return Member


def _get_unfold_context(request):
    """Get Unfold theme context (colors, border_radius, theme) from the admin site."""
    site = admin.site
    if hasattr(site, "each_context"):
        ctx = site.each_context(request)
        return {k: ctx[k] for k in ("colors", "border_radius", "theme") if k in ctx}
    return {}


class AcceptInvitationView(View):
    """Standalone Django view for accepting admin invitations."""

    def get(self, request, token):
        invitation = self._get_invitation(token)
        if invitation is None:
            return render(request, "authn/invitation/invalid.html", _get_unfold_context(request), status=400)

        contact = (
            ContactEmail.objects.filter(email_address__iexact=invitation.email, verified=True)
            .select_related("member")
            .first()
        )
        existing = contact.member if contact else None
        if existing:
            self._upgrade_member(existing, invitation)
            return render(
                request,
                "authn/invitation/already_registered.html",
                {"email": invitation.email, **_get_unfold_context(request)},
            )

        form = AcceptInvitationForm(initial={"email": invitation.email})
        return render(
            request,
            "authn/invitation/accept.html",
            {"form": form, "invitation": invitation, **_get_unfold_context(request)},
        )

    def post(self, request, token):
        invitation = self._get_invitation(token)
        if invitation is None:
            return render(request, "authn/invitation/invalid.html", _get_unfold_context(request), status=400)

        contact = (
            ContactEmail.objects.filter(email_address__iexact=invitation.email, verified=True)
            .select_related("member")
            .first()
        )
        existing = contact.member if contact else None
        if existing:
            self._upgrade_member(existing, invitation)
            return render(
                request,
                "authn/invitation/already_registered.html",
                {"email": invitation.email, **_get_unfold_context(request)},
            )

        form = AcceptInvitationForm(request.POST, initial={"email": invitation.email})
        if not form.is_valid():
            return render(
                request,
                "authn/invitation/accept.html",
                {"form": form, "invitation": invitation, **_get_unfold_context(request)},
            )

        # noinspection PyPep8Naming
        MemberModel = _get_member_model()
        member = MemberModel(
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            organization=form.cleaned_data.get("organization", ""),
            is_staff=True,
            is_active=True,
        )
        member.set_password(form.cleaned_data["password1"])
        member.save()

        ContactEmail.objects.create(
            member=member,
            email_address=invitation.email,
            email_type="primary",
            verified=True,
            subscribe=True,
        )

        invitation.mark_accepted(member)
        return render(
            request,
            "authn/invitation/success.html",
            {"member": member, **_get_unfold_context(request)},
        )

    # noinspection PyMethodMayBeStatic
    def _get_invitation(self, token):
        try:
            invitation = AdminInvitation.objects.get(token=token)
        except AdminInvitation.DoesNotExist:
            return None

        if not invitation.is_valid:
            if invitation.status == AdminInvitation.Status.PENDING and invitation.is_expired:
                invitation.mark_expired()
            return None

        return invitation

    # noinspection PyMethodMayBeStatic
    def _upgrade_member(self, member, invitation):
        member.is_staff = True
        member.save(update_fields=["is_staff", "updated_at"])
        invitation.mark_accepted(member)
