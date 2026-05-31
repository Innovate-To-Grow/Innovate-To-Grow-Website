from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import CliAccessToken


class CliTokenAuthentication(BaseAuthentication):
    """Bearer-token authentication for the /admin-api/ surface.

    A token is accepted only when it is unrevoked, unexpired, and owned by an
    active staff member. ``is_active`` and ``is_staff`` are re-checked on every
    request so a demotion takes effect immediately. A SimpleJWT bearer token will
    not match any stored hash and is therefore rejected here, ensuring the global
    JWT default never grants access to /admin-api/.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None
        if len(header) == 1:
            raise AuthenticationFailed("Invalid bearer header: no credentials provided.")
        if len(header) > 2:
            raise AuthenticationFailed("Invalid bearer header: token may not contain spaces.")
        raw = header[1].decode("latin-1")
        token = (
            CliAccessToken.objects.filter(token_hash=CliAccessToken.hash_token(raw)).select_related("member").first()
        )
        if token is None or not token.is_valid:
            raise AuthenticationFailed("Invalid or expired token.")
        member = token.member
        if not (member.is_active and member.is_staff):
            raise AuthenticationFailed("Token owner is not an active staff member.")
        token.touch_last_used()
        return (member, token)

    def authenticate_header(self, request):
        return 'Bearer realm="admin-api"'
