"""
View for accepting admin invitations (plain Django, not DRF).
"""

from django.shortcuts import render
from django.views import View

from authn.forms.invitation import AcceptInvitationForm
from authn.models.members.admin_invitation import AdminInvitation

Member = None  # resolved lazily


def _get_member_model():
    global Member
    if Member is None:
        from django.contrib.auth import get_user_model

        Member = get_user_model()
    return Member


class AcceptInvitationView(View):
    """Standalone Django view for accepting admin invitations."""

    def get(self, request, token):
        invitation = self._get_invitation(token)
        if invitation is None:
            return render(request, "authn/invitation/invalid.html", status=400)

        MemberModel = _get_member_model()
        existing = MemberModel.objects.filter(email__iexact=invitation.email).first()
        if existing:
            self._upgrade_member(existing, invitation)
            return render(request, "authn/invitation/already_registered.html", {"email": invitation.email})

        form = AcceptInvitationForm(initial={"email": invitation.email})
        return render(request, "authn/invitation/accept.html", {"form": form, "invitation": invitation})

    def post(self, request, token):
        invitation = self._get_invitation(token)
        if invitation is None:
            return render(request, "authn/invitation/invalid.html", status=400)

        MemberModel = _get_member_model()
        existing = MemberModel.objects.filter(email__iexact=invitation.email).first()
        if existing:
            self._upgrade_member(existing, invitation)
            return render(request, "authn/invitation/already_registered.html", {"email": invitation.email})

        form = AcceptInvitationForm(request.POST, initial={"email": invitation.email})
        if not form.is_valid():
            return render(request, "authn/invitation/accept.html", {"form": form, "invitation": invitation})

        member = MemberModel(
            email=invitation.email,
            username=form.cleaned_data["username"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            organization=form.cleaned_data.get("organization", ""),
            is_staff=True,
            is_superuser=(invitation.role == AdminInvitation.Role.SUPERUSER),
            is_active=True,
        )
        member.set_password(form.cleaned_data["password1"])
        member.save()

        invitation.mark_accepted(member)
        return render(request, "authn/invitation/success.html", {"member": member})

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

    def _upgrade_member(self, member, invitation):
        member.is_staff = True
        if invitation.role == AdminInvitation.Role.SUPERUSER:
            member.is_superuser = True
        member.save(update_fields=["is_staff", "is_superuser", "updated_at"])
        invitation.mark_accepted(member)
