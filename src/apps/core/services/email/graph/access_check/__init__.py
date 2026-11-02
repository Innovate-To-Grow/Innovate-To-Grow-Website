"""Check what Microsoft lets the Entra app do, against the InfoSec approval (Mail.Send + Mail.Read, scoped mailboxes).

One run, from ``manage.py verify_graph_access`` or the admin's "Run access check", is recorded as a
``MicrosoftGraphAccessCheck`` row, which the production go-live gate requires. In order:

1. A fresh token with the current certificate, and its ``roles`` read without trusting it (``roles``): FAIL for any
   role beyond ``GRAPH_APPROVED_APPLICATION_ROLES`` unless an InfoSec exception reference is recorded; WARN when
   the token claims none (RBAC for Applications grants never appear in it); INCONCLUSIVE (not a complete
   validation) when they cannot be read.
2. Each read-scoped mailbox: the Inbox folder, the newest message with its preview, and the start of its raw MIME
   (``$value``), as the admin inbox opens it; an empty Inbox leaves ``$value`` unexercised, which is INCONCLUSIVE. Each send-scoped mailbox listed by address: a MIME ``sendMail`` to
   itself, as the site sends most mail.
3. The deny mailbox: its Inbox folder and messages must be refused (403), sending as it must be refused, and a
   scoped mailbox must not send with the deny address as From (Send As / Send on Behalf). These sends are JSON with
   ``saveToSentItems`` false and are addressed to a scoped mailbox, so a wrongly accepted one files no copy and
   reaches only the I2G mailbox.

A refusal counts only when the same kind of request succeeded for a scoped mailbox in the same run (otherwise it is
INCONCLUSIVE), and a skipped probe is SKIP: either makes the run NOT A COMPLETE VALIDATION.
"""

from .evidence import record, run_and_record
from .probes import PROBE_SUBJECT
from .report import FAIL, INCONCLUSIVE, PASS, SKIP, WARN, AccessCheckReport, ProbeResult
from .roles import token_roles
from .runner import precondition_problem, run_access_check

__all__ = [
    "FAIL",
    "INCONCLUSIVE",
    "PASS",
    "PROBE_SUBJECT",
    "SKIP",
    "WARN",
    "AccessCheckReport",
    "ProbeResult",
    "precondition_problem",
    "record",
    "run_access_check",
    "run_and_record",
    "token_roles",
]
