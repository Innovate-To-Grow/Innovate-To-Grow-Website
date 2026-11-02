"""Each check of the Gmail API access check. Tokens are always fresh: none is cached, and the breadth tokens are
never used. Only the send probe sends mail (from each allowed account to itself, through the delivery-rate limiter).
"""

from types import SimpleNamespace

from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_UNCERTAIN
from apps.core.services.delivery_rates import RateDeferred, controlled

from ...contracts import EmailMessage
from ...exceptions import EmailDeliveryError, PermanentEmailDeliveryError
from ...registry import resolve_provider
from .. import auth, transport
from ..access import GmailScopeError, require_subject
from ..errors import DELEGATION_PENDING_CODES, GmailTokenRefused
from ..provider import GmailProvider
from .report import BREADTH, FAIL, KEY, PASS, REFUSAL, SEND, TOKEN, CheckResult

# A canary set of broader scopes, each requested alone: Google must refuse every one (unauthorized_client or
# access_denied). It cannot list every scope; the Admin console's "View details" of the delegation is authoritative.
GOOGLE_SCOPE = "https://www.googleapis.com/auth/"
BREADTH_SCOPES = (
    "https://mail.google.com/",
    *(
        f"{GOOGLE_SCOPE}gmail.{name}"
        for name in (
            "readonly",
            "modify",
            "compose",
            "insert",
            "metadata",
            "labels",
            "settings.basic",
            "settings.sharing",
            "addons.current.action.compose",
        )
    ),
    *(f"{GOOGLE_SCOPE}{name}" for name in ("cloud-platform", "admin.directory.user", "drive", "calendar")),
)
PROBE_SUBJECT = "I2G Gmail API access check"
PROBE_BODY = "Automated access check from the Innovate to Grow site. No action is needed."


def check_key(credential) -> tuple[CheckResult, object]:
    """The store returns the pinned version, and it matches the recorded service account and key id."""
    try:
        key = auth.read_signing_key(credential)
    except EmailDeliveryError as exc:
        return CheckResult(FAIL, KEY, credential.service_account_email, "readable", "error", str(exc)), None
    return CheckResult(
        PASS, KEY, credential.service_account_email, "readable", "read", f"key id {credential.key_id}"
    ), key


def check_token(credential, key, subject, *, timeout: float) -> tuple[CheckResult, str]:
    """A gmail.send token is issued for *subject*; returns the result and the token (for the send probe)."""
    try:
        grant = auth.request_token(credential, key, subject, timeout=timeout)
    except EmailDeliveryError as exc:
        return CheckResult(FAIL, TOKEN, subject.address, "issued", _got(exc), str(exc)), ""
    return CheckResult(PASS, TOKEN, subject.address, "issued", "issued"), grant.access_token


def check_refusal(config, deny_subject: str) -> CheckResult:
    """The site refuses an address off the allow-list before any key read or request; Google is not asked (it
    would grant the token by design: that token would be the very impersonation the list prevents)."""
    before = transport.requests_made()
    try:
        require_subject(config, deny_subject)
    except GmailScopeError:
        refused = True
    else:
        refused = False
    if not refused:
        return CheckResult(FAIL, REFUSAL, deny_subject, "refused", "allowed", "the address is on the allow-list")
    try:
        resolve_provider(SimpleNamespace(provider="gmail", from_email=deny_subject, from_name=""))
    except PermanentEmailDeliveryError:
        pass
    else:
        return CheckResult(FAIL, REFUSAL, deny_subject, "refused", "resolved", "the provider accepted the address")
    if transport.requests_made() != before:
        return CheckResult(FAIL, REFUSAL, deny_subject, "refused", "request", "a request was made for the address")
    return CheckResult(
        PASS, REFUSAL, deny_subject, "refused", "refused", "refused site-side (no request sent to Google)"
    )


def check_breadth(credential, key, subject, *, timeout: float) -> list[CheckResult]:
    results = []
    for scope in BREADTH_SCOPES:
        try:
            auth.request_token(credential, key, subject, timeout=timeout, scope=scope)
        except GmailTokenRefused as exc:
            outcome = PASS if exc.code in DELEGATION_PENDING_CODES else FAIL
            results.append(CheckResult(outcome, BREADTH, scope, "refused", exc.code or "refused"))
            continue
        except EmailDeliveryError as exc:
            results.append(CheckResult(FAIL, BREADTH, scope, "refused", _got(exc), f"inconclusive: {exc}"))
            continue
        # The token is discarded unused.
        note = f"DELEGATION BROADER THAN gmail.send: {scope}"
        results.append(CheckResult(FAIL, BREADTH, scope, "refused", "issued", note))
    return results


def check_send(credential, subject, access_token: str, *, timeout: float) -> CheckResult:
    """A probe from *subject* to itself, admitted through the limiter (it counts against the daily budget)."""
    provider = GmailProvider(credential=credential, subject=subject, from_email=subject.address, timeout=timeout)
    message = EmailMessage(subject=PROBE_SUBJECT, to=(subject.address,), text_body=PROBE_BODY)
    try:
        with controlled(
            provider.rate_channel,
            provider.rate_identity(),
            classify=lambda exc: getattr(exc, "rate_signal", None),
            **provider.rate_costs(message),
        ):
            provider.send_with_token(message, access_token)
    except RateDeferred as exc:
        note = f"held back by the delivery rate; try again in about {exc.retry_after} s"
        return CheckResult(FAIL, SEND, subject.address, "200 SENT", "deferred", note)
    except EmailDeliveryError as exc:
        unknown = exc.outcome == PROVIDER_OUTCOME_UNCERTAIN
        got, note = ("unknown", "outcome unknown") if unknown else (_got(exc), str(exc))
        return CheckResult(FAIL, SEND, subject.address, "200 SENT", got, note)
    if not provider.last_sent_label:
        return CheckResult(FAIL, SEND, subject.address, "200 SENT", "200", "Gmail did not report the SENT label")
    return CheckResult(PASS, SEND, subject.address, "200 SENT", "200 SENT", "probe sent to itself")


def _got(exc: EmailDeliveryError) -> str:
    return getattr(exc, "code", "") or exc.outcome
