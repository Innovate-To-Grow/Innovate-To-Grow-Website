from django.db import transaction

from apps.core.services.db_tools.safe_orm import (
    ActionRequestError,
    assign_model_fields,
    cascade_summary,
    collect_cascade_impact,
    json_safe,
    record_repr,
    serialize_model_instance,
    validate_write_payload,
)

from .audit import write_audit
from .resolve import cli_get_object, resolve_cli_model


class StaleSnapshotError(ActionRequestError):
    """Raised when the supplied X-Expected-Snapshot no longer matches the row (→409)."""


class CascadeNotConfirmedError(ActionRequestError):
    """Raised when a delete would cascade but confirm_cascade was not supplied (→400)."""


def _check_snapshot(model, before, expected_snapshot):
    if expected_snapshot is not None and json_safe(expected_snapshot) != json_safe(before):
        raise StaleSnapshotError(f"{model._meta.label} changed since the snapshot was taken; refetch and retry.")


def cli_create(*, actor, request_ip, app_label, model_name, fields):
    model = resolve_cli_model(app_label, model_name, write=True)
    if not isinstance(fields, dict) or not fields:
        raise ActionRequestError("fields must be a non-empty object.")
    clean = validate_write_payload(model, fields)
    with transaction.atomic():
        obj = model()
        assign_model_fields(obj, clean)
        obj.full_clean()
        obj.save()
        write_audit(
            actor=actor,
            action="create",
            status="success",
            app_label=model._meta.app_label,
            model_name=model._meta.model_name,
            target_pk=str(obj.pk),
            target_repr=record_repr(obj),
            changes=clean,
            request_ip=request_ip,
        )
    return obj


def cli_update(*, actor, request_ip, app_label, model_name, pk, changes, expected_snapshot=None):
    model = resolve_cli_model(app_label, model_name, write=True)
    if not isinstance(changes, dict) or not changes:
        raise ActionRequestError("changes must be a non-empty object.")
    with transaction.atomic():
        obj = cli_get_object(model, pk)
        before = serialize_model_instance(obj, write=True)
        _check_snapshot(model, before, expected_snapshot)
        clean = validate_write_payload(model, changes)
        assign_model_fields(obj, clean)
        obj.full_clean()
        obj.save()
        write_audit(
            actor=actor,
            action="update",
            status="success",
            app_label=model._meta.app_label,
            model_name=model._meta.model_name,
            target_pk=str(obj.pk),
            target_repr=record_repr(obj),
            changes=clean,
            before_snapshot=before,
            request_ip=request_ip,
        )
    return obj


def cli_delete(*, actor, request_ip, app_label, model_name, pk, confirm_cascade=False, expected_snapshot=None):
    model = resolve_cli_model(app_label, model_name, write=True)
    with transaction.atomic():
        obj = cli_get_object(model, pk)
        before = serialize_model_instance(obj, write=True)
        _check_snapshot(model, before, expected_snapshot)
        cascade = collect_cascade_impact(obj)
        if cascade.get("total", 0) > 0 and not confirm_cascade:
            raise CascadeNotConfirmedError(cascade_summary("Refusing to delete without confirm_cascade.", cascade))
        target_pk = str(obj.pk)
        target_repr = record_repr(obj)
        obj.delete()
        write_audit(
            actor=actor,
            action="delete",
            status="success",
            app_label=model._meta.app_label,
            model_name=model._meta.model_name,
            target_pk=target_pk,
            target_repr=target_repr,
            before_snapshot=before,
            cascade=cascade,
            request_ip=request_ip,
        )
    return {"deleted": True, "target_pk": target_pk, "cascade": cascade}
