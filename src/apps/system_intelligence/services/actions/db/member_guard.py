"""Member writes through an approved action stay on the staff side of the staff/superuser line.

``check_model_permission`` checks only the section grant. Without this, a staffer holding the Members (``authn``) grant
could use the assistant to change or delete another staff or superuser account, or to give themselves more admin
sections. The rules are stricter than ``MemberAdmin``'s, which still lets a staffer edit the name, title or
organization of another staff account (it locks only staff status, the admin sections and Active there):

* only the I2G Master changes or deletes another staff or superuser account through the assistant
  (``user_can_manage_member``; anyone may change their own);
* only the I2G Master writes the superuser-only fields (``MemberAdmin.superuser_only_fields``: staff status and the
  admin sections).

Contact rows and verification challenges are not writable through the assistant at all (safe_orm's
``DENIED_WRITE_MODEL_LABELS``). A proposal is refused at once; approval checks again, on the locked target row, and a
refused approval fails the request with the rule (``ActionRefused``).
"""

from __future__ import annotations

from apps.core.utils.access import user_can_manage_member
from apps.system_intelligence.models import SystemIntelligenceActionRequest

from ..exceptions import ActionRefused
from ..orm import get_object

MEMBER_LABEL = "authn.member"
TARGET_REFUSED = "Only an I2G Master may change or delete another staff or superuser account."


def is_member_model(model) -> bool:
    return model._meta.label_lower == MEMBER_LABEL


def check_member_write(user, model, *, fields=None, target=None) -> None:
    """Raise ``ActionRefused`` unless ``user`` may write ``fields`` on ``target`` (None for a new member)."""
    if not is_member_model(model):
        return
    if target is not None and not user_can_manage_member(user, target):
        raise ActionRefused(TARGET_REFUSED)
    if getattr(user, "is_superuser", False):
        return
    from apps.authn.admin.members.member import MemberAdmin

    refused = sorted(set(fields or ()) & set(MemberAdmin.superuser_only_fields))
    if refused:
        raise ActionRefused(f"Only an I2G Master may change {', '.join(refused)}.")


def check_member_action(user, model, action: SystemIntelligenceActionRequest) -> None:
    """``check_member_write`` for a pending action, at approval. The target row is locked first and the apply reads it
    again in the same transaction, so its staff status can't change between this check and the write."""
    if not is_member_model(model):
        return
    payload = action.payload if isinstance(action.payload, dict) else {}
    if action.action_type == SystemIntelligenceActionRequest.ACTION_DB_CREATE:
        check_member_write(user, model, fields=_names(payload.get("fields")))
        return
    target = get_object(model, action.target_pk, for_update=True)
    is_update = action.action_type == SystemIntelligenceActionRequest.ACTION_DB_UPDATE
    check_member_write(user, model, fields=_names(payload.get("changes")) if is_update else (), target=target)


def _names(values) -> tuple[str, ...]:
    # A malformed payload is refused by the apply itself; it names no field here.
    return tuple(values) if isinstance(values, dict) else ()
