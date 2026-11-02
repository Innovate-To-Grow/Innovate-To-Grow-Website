"""Judge one Graph answer to an access-check probe: PASS or FAIL, with a fixed note and no response text."""

import json

from ..errors import graph_error_code, request_id
from ..mailbox import is_message_id
from .report import ALLOWED, DENIED, FAIL, PASS, ProbeResult, join_notes

ACCESS_GRANTED = (
    "ACCESS WAS GRANTED: either the tenant-side restriction is missing or this address is another name of a "
    "scoped mailbox"
)
NOT_FOUND = "mailbox not found: use an existing mailbox outside the scope"
# Exchange starts its message with this when an Application Access Policy refuses the app (sometimes followed by
# detail such as "[RAOP]"); an EWS access policy, for example one that blocks a User-Agent, gives the same message.
ACCESS_POLICY_MESSAGE = "access to odata is disabled"
ACCESS_POLICY_NOTE = (
    "refused with 'Access to OData is disabled', as an Exchange Application Access Policy refuses (an EWS access "
    "policy gives the same message)"
)


def judge(check, mailbox, response, *, allowed_status: int, expect_allowed: bool) -> ProbeResult:
    status = response.status
    if expect_allowed:
        outcome, note = (PASS, "") if status == allowed_status else (FAIL, "")
    elif status == 403:
        outcome, note = PASS, ""
    else:
        outcome = FAIL
        note = ACCESS_GRANTED if status == allowed_status else (NOT_FOUND if status == 404 else "")
    if status == 403 and access_policy_refusal(response.body):
        note = join_notes(note, ACCESS_POLICY_NOTE)
    return ProbeResult(
        check,
        mailbox,
        ALLOWED if expect_allowed else DENIED,
        outcome,
        status=status,
        code=graph_error_code(response.body),
        note=note,
        request_id=request_id(response.headers),
    )


def access_policy_refusal(body: bytes) -> bool:
    """Whether a 403 body carries Exchange's access-policy message (compared, never echoed)."""
    try:
        error = json.loads(body).get("error")
    except (ValueError, AttributeError, RecursionError):
        return False
    message = error.get("message") if isinstance(error, dict) else None
    return isinstance(message, str) and message.strip().lower().startswith(ACCESS_POLICY_MESSAGE)


def newest_id(response) -> str:
    """The id of the newest message in a list answer, or "" (a truncated or unexpected answer gives none)."""
    try:
        messages = json.loads(response.body)["value"]
    except (ValueError, KeyError, TypeError, RecursionError):
        return ""
    if response.truncated or not isinstance(messages, list) or not messages or not isinstance(messages[0], dict):
        return ""
    message_id = messages[0].get("id")
    return message_id if is_message_id(message_id) else ""
