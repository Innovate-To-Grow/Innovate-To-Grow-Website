"""Result lines of the Gmail API access check, and its verdict."""

from dataclasses import dataclass, field
from datetime import datetime

PASS = "PASS"  # nosec B105 - an outcome label, not a credential
FAIL = "FAIL"
SKIP = "SKIP"
CONFIG = "config"
KEY = "key"
TOKEN = "token"  # nosec B105 - the name of a check, not a credential
REFUSAL = "refusal"
BREADTH = "breadth"
SEND = "send"
# Checks 1-5: all must pass (breadth included) for the run to count as evidence.
EVIDENCE_CHECKS = (CONFIG, KEY, TOKEN, REFUSAL, BREADTH)
DELEGATION_NOTE = (
    "Google-side per-user restriction: not available for domain-wide delegation; the site allow-list is the "
    "per-user control, and it does not bind anyone who holds the key."
)


@dataclass(frozen=True)
class CheckResult:
    outcome: str
    check: str
    subject: str
    expected: str
    got: str
    note: str = ""

    def line(self) -> str:
        line = f"{self.outcome:<5} {self.check:<8} {self.subject:<40} expected {self.expected:<10} got {self.got}"
        return f"{line}  ({self.note})" if self.note else line


@dataclass
class AccessReport:
    checked_at: datetime
    service_account_email: str
    client_id: str
    key_id: str
    key_version_id: str
    deny_subject: str
    breadth: bool
    send: bool
    results: list[CheckResult] = field(default_factory=list)
    # Whether this run wrote ``access_checked_at`` (checks 1-5 passed, the key unchanged meanwhile).
    recorded: bool = False

    def add(self, result: CheckResult) -> CheckResult:
        self.results.append(result)
        return result

    @property
    def failed(self) -> bool:
        return any(result.outcome == FAIL for result in self.results)

    @property
    def evidence(self) -> bool:
        """Checks 1-5 all ran and passed."""
        ran = {result.check for result in self.results if result.outcome == PASS}
        failed = {result.check for result in self.results if result.outcome == FAIL}
        return self.breadth and set(EVIDENCE_CHECKS) <= ran and not failed & set(EVIDENCE_CHECKS)

    def summary(self) -> str:
        counts = {outcome: sum(r.outcome == outcome for r in self.results) for outcome in (PASS, FAIL, SKIP)}
        return f"{counts[PASS]} passed, {counts[FAIL]} failed, {counts[SKIP]} skipped"

    def conclusion(self) -> str:
        failed = {result.check for result in self.results if result.outcome == FAIL}
        if failed & set(EVIDENCE_CHECKS) or not {result.check for result in self.results} >= {CONFIG, KEY}:
            return "THE ACCESS CHECK FAILED: the key's access does not match gmail.send for the allow-list."
        if not self.evidence:
            return "NOT A COMPLETE VALIDATION: the scope-breadth check was skipped, so nothing was recorded."
        if SEND in failed:
            return "Checks 1-5 passed and were recorded as evidence, but the send probe FAILED."
        return "The key's access matches gmail.send for the allow-list; recorded as the access check evidence."
