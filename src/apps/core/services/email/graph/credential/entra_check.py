"""Test a certificate against Microsoft Entra before the site relies on it: one client-credentials token request.

The token is discarded; only the outcome and the identity platform's allow-listed error code are kept. Error
numbers are from Microsoft Learn, "Microsoft Entra authentication and authorization error codes":

- AADSTS700027 "Client assertion failed signature validation": Entra does not (yet) trust the certificate, as
  before OIT registers it on the app. Not fatal for a config that is not sending.
- AADSTS700016 (application not found in the tenant), AADSTS90002 (tenant not found) and AADSTS7000112
  (application disabled): the tenant or app is wrong, so the change is refused before anything is stored.
"""

import re
from dataclasses import dataclass

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from ...exceptions import TransientEmailDeliveryError
from .. import auth, transport
from ..certificate import build_client_assertion
from ..errors import identity_error_code

OK = "ok"
NOT_TRUSTED = "not_trusted"
UNREACHABLE = "unreachable"
WRONG_APP = "wrong_app"
WRONG_TENANT = "wrong_tenant"
APP_DISABLED = "app_disabled"
REJECTED = "rejected"

# Outcomes after which nothing may be stored or pinned: the certificate cannot work for this tenant and app.
REFUSING_OUTCOMES = frozenset({WRONG_APP, WRONG_TENANT, APP_DISABLED, REJECTED})
_OUTCOME_BY_AADSTS = {700027: NOT_TRUSTED, 700016: WRONG_APP, 90002: WRONG_TENANT, 7000112: APP_DISABLED}
_AADSTS_RE = re.compile(r"AADSTS([0-9]{1,8})\b")
_RETRYABLE_STATUSES = {408, 429, 503}

DESCRIPTIONS = {
    OK: "Entra issued a token with this certificate.",
    NOT_TRUSTED: "Entra does not trust this certificate yet: it is not registered on the app.",
    UNREACHABLE: "Microsoft Entra could not be reached to test this certificate.",
    WRONG_APP: "Entra has no application with this client ID in the tenant.",
    WRONG_TENANT: "Entra does not know this tenant.",
    APP_DISABLED: "The Entra application is disabled.",
    REJECTED: "Entra rejected this certificate.",
}


@dataclass(frozen=True)
class EntraCheckResult:
    outcome: str
    code: str = ""

    @property
    def accepted(self) -> bool:
        return self.outcome == OK

    @property
    def refuses_change(self) -> bool:
        return self.outcome in REFUSING_OUTCOMES

    def describe(self) -> str:
        detail = f" ({self.code})" if self.code else ""
        return f"{DESCRIPTIONS[self.outcome]}{detail}"


@sensitive_variables()
def check_certificate(*, tenant_id: str, client_id: str, private_key: rsa.RSAPrivateKey, x5t_s256: str):
    """Request one token with *private_key* (held in memory only) and classify the answer."""
    try:
        assertion = build_client_assertion(
            tenant_id=tenant_id, client_id=client_id, private_key=private_key, x5t_s256=x5t_s256
        )
    except (ValueError, TypeError, UnsupportedAlgorithm):
        return EntraCheckResult(REJECTED)
    timeout = settings.GRAPH_CERTIFICATE_CHECK_TIMEOUT_SECONDS
    try:
        response = auth.post_token_request(tenant_id, client_id, assertion, timeout=timeout)
    except (transport.ConnectFailed, transport.ResponseLost):
        return EntraCheckResult(UNREACHABLE)
    return classify(response)


def classify(response: transport.HttpResponse) -> EntraCheckResult:
    if response.status == 200:
        try:
            auth.parse_access_token(response.body)
        except TransientEmailDeliveryError:
            return EntraCheckResult(UNREACHABLE)
        return EntraCheckResult(OK)
    if response.status in _RETRYABLE_STATUSES or response.status >= 500:
        return EntraCheckResult(UNREACHABLE)
    code = identity_error_code(response.body)
    match = _AADSTS_RE.search(code)
    outcome = _OUTCOME_BY_AADSTS.get(int(match.group(1)), REJECTED) if match else REJECTED
    return EntraCheckResult(outcome, code)
