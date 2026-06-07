"""Issue and revoke emailed login-link tokens (campaign and ticket emails)."""

from django.conf import settings
from django.utils import timezone

from apps.mail.models import LoginLinkToken
from apps.mail.utils.redirects import is_safe_internal_redirect_path

LOGIN_LINK_PATH = "/login-link"


def issue_login_link(*, member_id, validity_days, campaign=None, registration=None, redirect_path="") -> str:
    """Create a login-link token and return the absolute frontend URL for it.

    The validity is frozen onto the token at issue time; the reusable policy is
    intentionally NOT stamped here — it is read live from the issuing source at
    login time (see ``LoginLinkToken.is_reusable``) so it doubles as a kill switch.
    """
    token = LoginLinkToken.generate_token()
    LoginLinkToken.objects.create(
        token=token,
        member_id=member_id,
        campaign=campaign,
        registration=registration,
        redirect_path=redirect_path.strip() if is_safe_internal_redirect_path(redirect_path) else "",
        expires_at=timezone.now() + timezone.timedelta(days=validity_days),
    )
    frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    return f"{frontend_url}{LOGIN_LINK_PATH}?token={token}"


def revoke_login_links(queryset) -> int:
    """Expire every token in the queryset immediately. Returns the number revoked."""
    return queryset.filter(expires_at__gt=timezone.now()).update(expires_at=timezone.now())
