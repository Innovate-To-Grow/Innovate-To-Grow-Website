"""Run the Gmail API access check against the installed config (active or not) and record the evidence.

Checks, in order: 1 the config (an installed key and an allow-list), 2 the pinned key, 3 a gmail.send token for
each allowed account, 4 the site's refusal of an address off the list, 5 the breadth canary (unless skipped), and
6 a probe send per verified account (unless skipped). Evidence is written only for the key the run checked: each
token PASS writes that account's ``verified_at``; checks 1-5 all passing write ``access_checked_at``.
"""

import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.core.models import EmailServiceConfig, GmailApiProviderConfig, GmailApiSubject

from ..access import credential_for
from ..subject import issue
from . import checks
from .report import BREADTH, CONFIG, FAIL, PASS, SEND, SKIP, AccessReport, CheckResult

NOT_INSTALLED = "No Gmail API key is installed on this configuration."
NO_SUBJECTS = "The account allow-list is empty: add the From address first."


def precondition_problem(config) -> str:
    """Why the check cannot run on *config* yet, or ""."""
    if config._state.adding or not config.key_configured:
        return NOT_INSTALLED
    if not config.subjects.exists():
        return NO_SUBJECTS
    return ""


def default_deny_subject() -> str:
    """An address on the From domain that is certainly not on the list (nothing is sent to Google for it)."""
    domain = EmailServiceConfig.load().from_email.rpartition("@")[2] or "example.invalid"
    return f"site-refusal-probe-{secrets.token_hex(4)}@{domain}"


@sensitive_variables()
def run_access_check(config, *, deny_subject: str = "", send: bool = True, breadth: bool = True) -> AccessReport:
    report = AccessReport(
        checked_at=timezone.now(),
        service_account_email=config.service_account_email,
        client_id=config.client_id,
        key_id=config.key_id,
        key_version_id=config.key_version_id,
        deny_subject=deny_subject or default_deny_subject(),
        breadth=breadth,
        send=send,
    )
    problem = precondition_problem(config)
    if problem:
        report.add(CheckResult(FAIL, CONFIG, config.name, "configured", "missing", problem))
        return report
    report.add(CheckResult(PASS, CONFIG, config.name, "configured", "configured"))
    credential = credential_for(config)
    result, key = checks.check_key(credential)
    report.add(result)
    if key is None:
        return report
    timeout = settings.GMAIL_API["access_check_timeout_seconds"]
    verified = []
    for row in config.subjects.all():
        subject = issue(row.subject)  # the allow-list itself: every row is a listed subject
        result, token = checks.check_token(credential, key, subject, timeout=timeout)
        report.add(result)
        if token:
            verified.append((row, subject, token))
    report.add(checks.check_refusal(config, report.deny_subject))
    if not breadth:
        report.add(CheckResult(SKIP, BREADTH, "-", "refused", "skipped", "breadth check skipped"))
    elif verified:
        report.results.extend(checks.check_breadth(credential, key, verified[0][1], timeout=timeout))
    del key
    if not send:
        report.add(CheckResult(SKIP, SEND, "-", "200 SENT", "skipped", "send probe skipped"))
    for _row, subject, token in verified if send else ():
        report.add(checks.check_send(credential, subject, token, timeout=timeout))
    _record(config, report, [row.pk for row, _subject, _token in verified])
    return report


def _record(config, report: AccessReport, verified_pks: list) -> None:
    """Write the evidence, only if the config still pins the key this run checked."""
    now = timezone.now()
    with transaction.atomic():
        locked = GmailApiProviderConfig.objects.select_for_update().filter(pk=config.pk).first()
        if locked is None or locked.key_version_id != report.key_version_id:
            return
        GmailApiSubject.objects.filter(config=locked, pk__in=verified_pks).update(verified_at=now, updated_at=now)
        if report.evidence:
            GmailApiProviderConfig.objects.filter(pk=locked.pk).update(access_checked_at=now, updated_at=now)
            report.recorded = True
    config.refresh_from_db()
