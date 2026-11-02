"""The Gmail API access check: what Google lets the installed key do, recorded as the go-live evidence.

- ``report``: the result lines and the verdict; ``checks``: each check (key, tokens, site refusal, breadth, send);
- ``runner``: runs them against the installed config (active or not) and writes the evidence: each subject's
  ``verified_at`` on a token PASS, and the config's ``access_checked_at`` when checks 1-5 all pass.
"""

from .report import FAIL, PASS, SKIP, AccessReport, CheckResult
from .runner import precondition_problem, run_access_check

__all__ = ["FAIL", "PASS", "SKIP", "AccessReport", "CheckResult", "precondition_problem", "run_access_check"]
