"""What one access check found: a ``ProbeResult`` per check, and the verdict they add up to."""

import dataclasses
import datetime
from dataclasses import dataclass

from apps.core.models import MicrosoftGraphAccessCheck

Verdict = MicrosoftGraphAccessCheck.Verdict

PASS, FAIL, WARN, SKIP, INCONCLUSIVE = "PASS", "FAIL", "WARN", "SKIP", "INCONCLUSIVE"
ISSUED, ALLOWED, DENIED, NOT_IN_SCOPE = "issued", "allowed", "denied (403)", "not in scope"
TOKEN, ROLES, FOLDER, MESSAGES, VALUE, SEND, SEND_AS = "token", "roles", "folder", "list", "value", "send", "sendas"
# Reading a mailbox the site may only send as: for the record (WARN when Microsoft allows it), never a verdict.
EXTRA_READ = "read+"
# The probes that show Microsoft's mailbox restriction. ``value`` (opening a message) only shows that reading works.
RESTRICTION_CHECKS = frozenset({FOLDER, MESSAGES, SEND, SEND_AS})
UNPAIRED = (
    "inconclusive: no {kind} request for a scoped mailbox succeeded in this run, so this refusal may mean the app "
    "has no access at all rather than a working restriction"
)


@dataclass(frozen=True)
class ProbeResult:
    check: str
    mailbox: str
    expected: str
    outcome: str
    status: int | None = None
    code: str = ""
    note: str = ""
    request_id: str = ""

    @property
    def passed(self) -> bool:
        return self.outcome == PASS

    @property
    def denial(self) -> bool:
        return self.expected == DENIED

    @property
    def kind(self) -> str:
        """Sending as another address is still a send: it pairs with the allowed send probe."""
        return SEND if self.check == SEND_AS else self.check

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def pair_denials(results) -> list[ProbeResult]:
    """A refusal counts only when the same kind of request succeeded for a scoped mailbox in the same run.

    Microsoft also answers 403 when the app may do nothing at all, so an unpaired refusal becomes INCONCLUSIVE.
    """
    shown = {result.kind for result in results if result.passed and not result.denial}
    return [
        dataclasses.replace(
            result, outcome=INCONCLUSIVE, note=join_notes(result.note, UNPAIRED.format(kind=result.kind))
        )
        if result.denial and result.passed and result.kind not in shown
        else result
        for result in results
    ]


def join_notes(*notes: str) -> str:
    return "; ".join(note for note in notes if note)


@dataclass(frozen=True)
class AccessCheckReport:
    """The probes of one run plus what identifies it: the app, the certificate, the deny mailbox and the time."""

    results: tuple[ProbeResult, ...]
    granted_roles: tuple[str, ...] | None
    approved_roles: tuple[str, ...]
    exception_reference: str
    tenant_id: str
    client_id: str
    certificate_id: object
    certificate_sha1: str
    key_version_id: str
    deny_mailbox: str
    checked_at: datetime.datetime
    # Roles beyond the approval accepted as granted at the time of the run (``roles.accepted_broader_roles``).
    broader_roles: tuple[str, ...] = ()

    @property
    def token_issued(self) -> bool:
        return any(result.check == TOKEN and result.passed for result in self.results)

    @property
    def complete(self) -> bool:
        """The token was issued and no check was skipped or inconclusive."""
        return self.token_issued and not any(result.outcome in (SKIP, INCONCLUSIVE) for result in self.results)

    @property
    def restriction_holds(self) -> bool:
        restriction = [result for result in self.results if result.check in RESTRICTION_CHECKS]
        return self.token_issued and bool(restriction) and all(result.passed for result in restriction)

    @property
    def extra_roles(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.granted_roles or ()) - set(self.approved_roles)))

    @property
    def accepted_extra_roles(self) -> tuple[str, ...]:
        """The roles beyond the approval accepted as granted: broader roles that cover an approved one."""
        return tuple(role for role in self.extra_roles if role in self.broader_roles)

    @property
    def roles_within_approval(self) -> bool | None:
        """None when the token's roles could not be read (or no token was issued)."""
        if self.granted_roles is None:
            return None
        return not self.extra_roles

    @property
    def verdict(self) -> str:
        """Any FAIL (roles beyond the approval without an InfoSec exception included) does not match; otherwise a
        run with a skipped or inconclusive check, or without the restriction shown, is incomplete."""
        if any(result.outcome == FAIL for result in self.results):
            return Verdict.NOT_COMPLIANT
        if not (self.complete and self.restriction_holds):
            return Verdict.INCOMPLETE
        return Verdict.COMPLIANT

    def summary(self) -> str:
        if self.restriction_holds and self.complete:
            restriction = "HOLDS"
        elif any(result.outcome == FAIL for result in self.results if result.check in RESTRICTION_CHECKS):
            restriction = "FAILED"
        else:
            restriction = "NOT PROVEN"
        return f"Mailbox restriction: {restriction} · Granted roles: {self._roles_text()} · Verdict: {self._verdict_text()}"

    def conclusion(self) -> str:
        verdict = self.verdict
        if verdict == Verdict.INCOMPLETE:
            return (
                "NOT A COMPLETE VALIDATION: checks were skipped or inconclusive, so this run is not evidence that "
                "Microsoft's restriction holds."
            )
        if verdict == Verdict.NOT_COMPLIANT:
            return "Microsoft Graph access does NOT match the approval."
        if self.extra_roles:
            return f"The mailbox restriction holds; {self._extra_roles_conclusion()}."
        return (
            "Microsoft Graph access matches the approval: the mailbox restriction holds and the token claims no "
            "role beyond the approval."
        )

    def _roles_text(self) -> str:
        if self.granted_roles is None:
            return "NOT READABLE"
        if not self.granted_roles:
            return "NONE in the token (RBAC for Applications grants never appear there)"
        if not self.extra_roles:
            return "WITHIN the approval"
        accepted = self.accepted_extra_roles
        roles = (f"{role}: accepted broader grant" if role in accepted else role for role in self.extra_roles)
        return f"BEYOND the approval ({', '.join(roles)})"

    def _extra_roles_conclusion(self) -> str:
        accepted = self.accepted_extra_roles
        others = [role for role in self.extra_roles if role not in accepted]
        parts = []
        if accepted:
            parts.append(
                f"the token claims {', '.join(accepted)} beyond the approval, accepted as granted because it covers "
                "an approved role"
            )
        if others:
            parts.append(
                f"the token claims {', '.join(others)} beyond the approval, covered by InfoSec exception "
                f"{self.exception_reference}"
            )
        return "; ".join(parts)

    def _verdict_text(self) -> str:
        return {
            Verdict.COMPLIANT: "MATCHES THE APPROVAL",
            Verdict.NOT_COMPLIANT: "DOES NOT MATCH THE APPROVAL",
            Verdict.INCOMPLETE: "NOT A COMPLETE VALIDATION",
        }[self.verdict]
