"""The rules for Member writes through an approved assistant action.

Every Admin may change any member through the assistant, another Admin included. Two things stay off this path:

* Admin status (``is_staff``, and its mirror ``is_superuser``) changes only on the member's page in the admin. safe_orm
  already denies both field names; this refuses an action stored with them before it reaches the write;
* the lockout rules (``admin_removal_refusal``): nobody deletes or deactivates (``is_active`` set false) their own Admin
  account, and the last active Admin is never deleted or deactivated.

Contact rows and verification challenges are not writable through the assistant at all (safe_orm's
``DENIED_WRITE_MODEL_LABELS``). A proposal is refused at once; approval checks again, on the locked target row, and a
refused approval fails the request with the rule (``ActionRefused``).
"""

from __future__ import annotations

from apps.authn.services.members.admins import DEACTIVATE, DELETE, admin_removal_refusal
from apps.system_intelligence.models import SystemIntelligenceActionRequest

from ..engine.exceptions import ActionRefused
from ..orm import get_object
from ..orm.safety import coerce_field_value

MEMBER_LABEL = "authn.member"
ADMIN_STATUS_FIELDS = frozenset({"is_staff", "is_superuser"})
ADMIN_STATUS_REFUSED = "Admin status is changed only on the member's page in the admin, not through the assistant."


def is_member_model(model) -> bool:
    return model._meta.label_lower == MEMBER_LABEL


def check_member_write(user, model, *, fields=None, target=None, delete=False) -> None:
    """Raise ``ActionRefused`` unless ``user`` may write ``fields`` (name -> value) on ``target`` (None for a new
    member), or delete ``target`` when ``delete`` is set."""
    if not is_member_model(model):
        return
    fields = fields or {}
    if ADMIN_STATUS_FIELDS & set(fields):
        raise ActionRefused(ADMIN_STATUS_REFUSED)
    if target is None:
        return
    if delete:
        refusal = admin_removal_refusal(user, [target], action=DELETE)
    elif "is_active" in fields and coerce_field_value(model._meta.get_field("is_active"), fields["is_active"]) is False:
        refusal = admin_removal_refusal(user, [target], action=DEACTIVATE)
    else:
        refusal = ""
    if refusal:
        raise ActionRefused(refusal)


def check_member_action(user, model, action: SystemIntelligenceActionRequest) -> None:
    """``check_member_write`` for a pending action, at approval. The target row is locked first and the apply reads it
    again in the same transaction, so its Admin status can't change between this check and the write."""
    if not is_member_model(model):
        return
    payload = action.payload if isinstance(action.payload, dict) else {}
    if action.action_type == SystemIntelligenceActionRequest.ACTION_DB_CREATE:
        check_member_write(user, model, fields=_values(payload.get("fields")))
        return
    target = get_object(model, action.target_pk, for_update=True)
    if action.action_type == SystemIntelligenceActionRequest.ACTION_DB_UPDATE:
        check_member_write(user, model, fields=_values(payload.get("changes")), target=target)
    else:
        check_member_write(user, model, target=target, delete=True)


def _values(values) -> dict:
    # A malformed payload is refused by the apply itself; it names no field here.
    return values if isinstance(values, dict) else {}
