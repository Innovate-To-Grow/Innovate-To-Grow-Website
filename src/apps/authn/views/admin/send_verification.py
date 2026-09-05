"""Keep admin verification challenges inside the remembered cookie's path."""

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

from apps.authn.services.send_verification.constants import (
    OP_ADMIN_LOGIN_REMEMBERED_CODE,
    OP_ADMIN_LOGIN_REQUEST_CODE,
    OP_ADMIN_LOGIN_RESEND,
)
from apps.authn.views.auth.send_verification import SendVerificationChallengeView


@method_decorator(csrf_protect, name="dispatch")
class AdminSendVerificationChallengeView(SendVerificationChallengeView):
    allowed_operations = frozenset({OP_ADMIN_LOGIN_REQUEST_CODE, OP_ADMIN_LOGIN_REMEMBERED_CODE, OP_ADMIN_LOGIN_RESEND})
