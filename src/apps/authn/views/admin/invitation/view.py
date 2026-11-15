"""The invitation page: show the form, accept it (plain Django, not DRF)."""

from django.contrib import admin
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from apps.authn.forms.invitation import AcceptInvitationForm
from apps.core.services.request_limits.view_limits import view_rate

from .membership import InvitationEmailConflict, InvitationMembershipMixin

# Attempts per invitation and period: the live "view-invitation" request-limit policy (10 per hour by default).
INVITATION_RATE_POLICY = "view-invitation"


def _get_unfold_context(request):
    """Get Unfold theme context (colors, border_radius, theme) from the admin site."""
    site = admin.site
    if hasattr(site, "each_context"):
        ctx = site.each_context(request)
        return {k: ctx[k] for k in ("colors", "border_radius", "theme") if k in ctx}
    return {}


class AcceptInvitationView(InvitationMembershipMixin, View):
    """Standalone Django view for accepting admin invitations."""

    rate_limit_scope = {"GET": "tokenized-link", "*": "auth-sign-in"}

    def get(self, request, token):
        invitation = self._get_invitation(token)
        if invitation is None:
            return render(request, "authn/invitation/invalid.html", _get_unfold_context(request), status=400)

        existing = self._get_verified_member(invitation)
        if existing:
            # Render a page that POSTs the upgrade; do NOT grant staff here. This used to run
            # _upgrade_member on the GET, so a mail-gateway link scanner or a browser prefetch
            # silently granted is_staff + is_active and burned the invitation — a privileged write on
            # an unauthenticated, CSRF-exempt request.
            return render(
                request,
                "authn/invitation/already_registered.html",
                {
                    "email": invitation.email,
                    "invitation": invitation,
                    "needs_confirmation": True,
                    **_get_unfold_context(request),
                },
            )

        form = AcceptInvitationForm(initial={"email": invitation.email})
        return render(
            request,
            "authn/invitation/accept.html",
            {"form": form, "invitation": invitation, **_get_unfold_context(request)},
        )

    def post(self, request, token):
        # Look the invitation up BEFORE counting. The token is part of the URL, so counting first would let an
        # anonymous caller mint one cache key (in production: one cache file) per made-up token. An unknown token
        # needs no attempt limit: it is a long random secret, and every miss gets the same "invalid" page.
        invitation = self._get_invitation(token)
        if invitation is None:
            return render(request, "authn/invitation/invalid.html", _get_unfold_context(request), status=400)

        rate = view_rate(INVITATION_RATE_POLICY)
        if rate is not None:
            cache_key = f"invitation-rate:{invitation.pk}"
            attempts = cache.get(cache_key, 0)
            if attempts >= rate.requests:
                return HttpResponse("Too many attempts. Please try again later.", status=429, content_type="text/plain")
            cache.set(cache_key, attempts + 1, timeout=rate.period)

        existing = self._get_verified_member(invitation)
        if existing:
            # The GET only offers the button; the privilege grant happens here, behind CSRF.
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

        try:
            self._create_member(form, invitation)
        except InvitationEmailConflict as exc:
            form.add_error("email", str(exc))
            return render(
                request,
                "authn/invitation/accept.html",
                {"form": form, "invitation": invitation, **_get_unfold_context(request)},
            )

        return render(
            request,
            "authn/invitation/success.html",
            {"member": self._created_member, **_get_unfold_context(request)},
        )
