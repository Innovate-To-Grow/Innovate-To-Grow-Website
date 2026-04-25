from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models

from .exceptions import ActionRequestError
from .orm_safety import field_output_name, safe_model_fields
from .utils import json_safe


def get_object(model: type[models.Model], pk: str) -> models.Model:
    try:
        return model.objects.get(pk=pk)
    except model.DoesNotExist as exc:
        raise ActionRequestError(f"{model._meta.label} record '{pk}' was not found.") from exc
    except (TypeError, ValueError, ValidationError) as exc:
        raise ActionRequestError(f"Invalid primary key for {model._meta.label}: {pk}") from exc


def serialize_model_instance(obj: models.Model, *, write: bool) -> dict:
    fields = safe_model_fields(obj.__class__, write=write)
    data = {field_output_name(field): json_safe(getattr(obj, field_output_name(field), None)) for field in fields}
    data["__repr__"] = record_repr(obj)
    return data


def record_repr(obj: models.Model) -> str:
    value = str(obj)
    return value[:300] if len(value) > 300 else value


def clone_model_instance(obj: models.Model) -> models.Model:
    clone = obj.__class__.objects.get(pk=obj.pk)
    clone._state.adding = False
    return clone


def check_model_permission(user, model: type[models.Model], action: str) -> None:
    if not user or not user.is_authenticated or not user.is_staff:
        raise PermissionDenied("Staff authentication is required.")
    if not user.has_perm(f"{model._meta.app_label}.{action}_{model._meta.model_name}"):
        raise PermissionDenied(f"You do not have permission to {action} {model._meta.verbose_name}.")


def assert_snapshot_unchanged(before: dict, current: dict, label: str) -> None:
    if before and json_safe(before) != json_safe(current):
        raise ActionRequestError(f"{label} changed after this request was proposed. Create a fresh proposal.")
