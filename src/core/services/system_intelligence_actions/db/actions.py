from typing import Any

from django.db import models

from core.models.base.system_intelligence import SystemIntelligenceActionRequest

from ..comparison import build_db_comparison, build_diff
from ..context import current_conversation, current_user_id
from ..exceptions import ActionRequestError
from ..orm import (
    assert_snapshot_unchanged,
    assign_model_fields,
    clone_model_instance,
    get_object,
    record_repr,
    resolve_model,
    serialize_model_instance,
    validate_write_payload,
)
from ..serialization import proposal_tool_response


def propose_db_create(app_label: str, model_name: str, fields: dict[str, Any], summary: str | None = None):
    """Create a pending single-record ORM create action."""
    conversation = current_conversation()
    model = resolve_model(app_label, model_name, write=True)
    if not isinstance(fields, dict) or not fields:
        raise ActionRequestError("fields must be a non-empty object.")
    clean_fields = validate_write_payload(model, fields)
    obj = model()
    assign_model_fields(obj, clean_fields)
    obj.full_clean()
    after = serialize_model_instance(obj, write=True)
    comparison = build_db_comparison(model, {}, after, mode="create")
    action = SystemIntelligenceActionRequest.objects.create(
        conversation=conversation,
        created_by_id=current_user_id(),
        action_type=SystemIntelligenceActionRequest.ACTION_DB_CREATE,
        target_app_label=model._meta.app_label,
        target_model=model._meta.object_name,
        target_repr=f"New {model._meta.verbose_name}",
        title=f"Create {model._meta.verbose_name}",
        summary=summary or "Review this new database record before applying it.",
        payload={
            "app_label": model._meta.app_label,
            "model_name": model._meta.object_name,
            "fields": clean_fields,
            "comparison": comparison,
        },
        before_snapshot={},
        after_snapshot=after,
        diff=build_diff({}, after),
    )
    return proposal_tool_response(action, "Database create request is ready for approval.")


def propose_db_update(app_label: str, model_name: str, pk: str, changes: dict[str, Any], summary: str | None = None):
    """Create a pending single-record ORM update action."""
    conversation = current_conversation()
    model = resolve_model(app_label, model_name, write=True)
    obj = get_object(model, pk)
    if not isinstance(changes, dict) or not changes:
        raise ActionRequestError("changes must be a non-empty object.")
    clean_changes = validate_write_payload(model, changes)
    before = serialize_model_instance(obj, write=True)
    proposed_obj = clone_model_instance(obj)
    assign_model_fields(proposed_obj, clean_changes)
    proposed_obj.full_clean()
    after = serialize_model_instance(proposed_obj, write=True)
    comparison = build_db_comparison(model, before, after, mode="update")
    action = SystemIntelligenceActionRequest.objects.create(
        conversation=conversation,
        created_by_id=current_user_id(),
        action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
        target_app_label=model._meta.app_label,
        target_model=model._meta.object_name,
        target_pk=str(obj.pk),
        target_repr=record_repr(obj),
        title=f"Update {model._meta.verbose_name}: {record_repr(obj)}",
        summary=summary or "Review this database update before applying it.",
        payload={
            "app_label": model._meta.app_label,
            "model_name": model._meta.object_name,
            "pk": str(obj.pk),
            "changes": clean_changes,
            "comparison": comparison,
        },
        before_snapshot=before,
        after_snapshot=after,
        diff=build_diff(before, after),
    )
    return proposal_tool_response(action, "Database update request is ready for approval.")


def propose_db_delete(app_label: str, model_name: str, pk: str, summary: str | None = None):
    """Create a pending single-record ORM delete action."""
    conversation = current_conversation()
    model = resolve_model(app_label, model_name, write=True)
    obj = get_object(model, pk)
    before = serialize_model_instance(obj, write=True)
    comparison = build_db_comparison(model, before, {}, mode="delete")
    action = SystemIntelligenceActionRequest.objects.create(
        conversation=conversation,
        created_by_id=current_user_id(),
        action_type=SystemIntelligenceActionRequest.ACTION_DB_DELETE,
        target_app_label=model._meta.app_label,
        target_model=model._meta.object_name,
        target_pk=str(obj.pk),
        target_repr=record_repr(obj),
        title=f"Delete {model._meta.verbose_name}: {record_repr(obj)}",
        summary=summary or "Review this database deletion before applying it.",
        payload={
            "app_label": model._meta.app_label,
            "model_name": model._meta.object_name,
            "pk": str(obj.pk),
            "comparison": comparison,
        },
        before_snapshot=before,
        after_snapshot={},
        diff=build_diff(before, {}),
    )
    return proposal_tool_response(action, "Database delete request is ready for approval.")


def apply_db_create(action: SystemIntelligenceActionRequest, model: type[models.Model]) -> None:
    fields = action.payload.get("fields")
    if not isinstance(fields, dict):
        raise ActionRequestError("Invalid create payload.")
    obj = model()
    assign_model_fields(obj, validate_write_payload(model, fields))
    obj.full_clean()
    obj.save()
    action.target_pk = str(obj.pk)
    action.target_repr = record_repr(obj)


def apply_db_update(action: SystemIntelligenceActionRequest, model: type[models.Model]) -> None:
    obj = get_object(model, action.target_pk)
    assert_snapshot_unchanged(action.before_snapshot, serialize_model_instance(obj, write=True), model._meta.label)
    changes = action.payload.get("changes")
    if not isinstance(changes, dict):
        raise ActionRequestError("Invalid update payload.")
    assign_model_fields(obj, validate_write_payload(model, changes))
    obj.full_clean()
    obj.save()
    action.target_repr = record_repr(obj)


def apply_db_delete(action: SystemIntelligenceActionRequest, model: type[models.Model]) -> None:
    obj = get_object(model, action.target_pk)
    assert_snapshot_unchanged(action.before_snapshot, serialize_model_instance(obj, write=True), model._meta.label)
    action.target_repr = record_repr(obj)
    obj.delete()
