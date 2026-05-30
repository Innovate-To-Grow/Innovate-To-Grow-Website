from urllib.parse import urlencode

from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..constants import ACCESS_TOKEN_TTL, CLI_CLIENT_ID, PKCE_METHOD
from ..models import CliAccessToken, CliAuthorizationCode
from ..pkce import verify_pkce_s256
from ..redirect_uri import RedirectUriError, validate_loopback_redirect_uri
from ..serializers import TokenExchangeSerializer
from ..throttles import CliOAuthThrottle
from .helpers import client_ip

ADMIN_LOGIN_PATH = "/admin/login/"


@method_decorator(never_cache, name="dispatch")
class OAuthAuthorizeView(View):
    """Authorization endpoint. Session-authenticated; bounces non-staff to the admin
    login with a same-host ``?next`` so the completed login redirects back here."""

    def get(self, request):
        user = request.user
        if not (user.is_authenticated and user.is_active and user.is_staff):
            login_url = f"{ADMIN_LOGIN_PATH}?{urlencode({'next': request.get_full_path()})}"
            return redirect(login_url)

        params = request.GET
        if params.get("response_type") != "code":
            return HttpResponseBadRequest("response_type must be 'code'.")
        if params.get("client_id") != CLI_CLIENT_ID:
            return HttpResponseBadRequest("Unknown client_id.")
        if params.get("code_challenge_method") != PKCE_METHOD:
            return HttpResponseBadRequest("code_challenge_method must be S256.")
        challenge = params.get("code_challenge") or ""
        if not 43 <= len(challenge) <= 128:
            return HttpResponseBadRequest("code_challenge has an invalid length.")
        redirect_uri = params.get("redirect_uri") or ""
        try:
            validate_loopback_redirect_uri(redirect_uri)
        except RedirectUriError as exc:
            return HttpResponseBadRequest(str(exc))

        state = params.get("state") or ""
        raw_code = CliAuthorizationCode.generate_raw_code()
        CliAuthorizationCode.objects.create(
            code_hash=CliAuthorizationCode.hash_code(raw_code),
            member=user,
            code_challenge=challenge,
            redirect_uri=redirect_uri,
        )
        query = urlencode({"code": raw_code, "state": state})
        return HttpResponseRedirect(f"{redirect_uri}?{query}")


def _invalid_grant():
    return Response({"error": "invalid_grant"}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name="dispatch")
class OAuthTokenView(APIView):
    """Token endpoint. Machine POST: no cookies/session; auth is code+verifier only."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [CliOAuthThrottle]

    def post(self, request):
        serializer = TokenExchangeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "invalid_request"}, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        if data["grant_type"] != "authorization_code":
            return Response({"error": "unsupported_grant_type"}, status=status.HTTP_400_BAD_REQUEST)
        if data["client_id"] != CLI_CLIENT_ID:
            return Response({"error": "invalid_client"}, status=status.HTTP_400_BAD_REQUEST)

        code = (
            CliAuthorizationCode.objects.filter(code_hash=CliAuthorizationCode.hash_code(data["code"]))
            .select_related("member")
            .first()
        )
        if code is None:
            return _invalid_grant()
        # Claim atomically BEFORE other checks so any failed attempt burns the code.
        if code.is_expired or not code.try_mark_used():
            return _invalid_grant()
        if not constant_time_compare(code.redirect_uri, data["redirect_uri"]):
            return _invalid_grant()
        if not verify_pkce_s256(data["code_verifier"], code.code_challenge):
            return _invalid_grant()
        member = code.member
        if not (member.is_active and member.is_staff):
            return _invalid_grant()

        raw_token = CliAccessToken.generate_raw_token()
        CliAccessToken.objects.create(
            token_hash=CliAccessToken.hash_token(raw_token),
            member=member,
            created_ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        )
        return Response(
            {
                "access_token": raw_token,
                "token_type": "Bearer",
                "expires_in": int(ACCESS_TOKEN_TTL.total_seconds()),
            }
        )
