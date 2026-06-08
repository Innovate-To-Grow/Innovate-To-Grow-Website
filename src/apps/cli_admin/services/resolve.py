from django.core.exceptions import ValidationError

from apps.core.access import user_can_access_app
from apps.core.services.db_tools.safe_orm import ActionRequestError, resolve_model

from ..constants import CLI_EXTRA_DENIED_APP_LABELS, CLI_EXTRA_DENIED_MODEL_LABELS


class CliAppAccessDenied(ActionRequestError):
    """Raised when an actor lacks per-app access to a model's app (→403).

    Distinct from the denylist ``ActionRequestError`` (→400): the model is
    reachable in principle, but this actor's ``admin_apps`` does not grant it.
    """


def is_cli_denied(model) -> bool:
    """True if a model is blocked by the CLI-specific extra denylist (app or label)."""
    return (
        model._meta.app_label in CLI_EXTRA_DENIED_APP_LABELS or model._meta.label_lower in CLI_EXTRA_DENIED_MODEL_LABELS
    )


def resolve_cli_model(app_label, model_name, *, write, actor=None):
    """Resolve a model for the CLI, enforcing the shared denylist plus the
    CLI-specific extra denylist (whole apps and individual labels).

    When ``actor`` is supplied, also enforce per-app admin access: the actor may
    only reach models whose app their ``admin_apps`` grants (superuser bypasses).
    A denial here is a 403 (``CliAppAccessDenied``), distinct from the 400 the
    denylist raises."""
    model = resolve_model(app_label, model_name, write=write)
    if is_cli_denied(model):
        access = "Write" if write else "Read"
        raise ActionRequestError(f"{access} access is not allowed for {model._meta.label}.")
    if actor is not None and not user_can_access_app(actor, model._meta.app_label):
        raise CliAppAccessDenied(f"You do not have access to the {model._meta.app_label} app.")
    return model


def cli_get_object(model, pk):
    """Fetch a row by pk. ``DoesNotExist`` propagates (mapped to 404 by the view);
    a malformed pk becomes an ``ActionRequestError`` (mapped to 400)."""
    try:
        return model.objects.get(pk=pk)
    except model.DoesNotExist:
        raise
    except (TypeError, ValueError, ValidationError) as exc:
        raise ActionRequestError(f"Invalid primary key for {model._meta.label}: {pk}") from exc
