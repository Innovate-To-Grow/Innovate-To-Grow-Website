import logging
import re
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from cms.models import CMSPage
from system_intelligence.models import SystemIntelligenceActionRequest

from .cms import apply_cms_page_update
from .db import apply_db_create, apply_db_delete, apply_db_update
from .exceptions import ActionRequestError
from .orm import check_model_permission, resolve_model

logger = logging.getLogger(__name__)

_ERROR_MESSAGE_MAX_LEN = 300
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_GENERIC_FAILURE_MESSAGE = "Action could not be applied. See server logs for details."


def approve_action_request(action_id: str | uuid.UUID, user) -> SystemIntelligenceActionRequest:
    """Apply a pending action request after permission and validation checks."""
    action = None
    try:
        with transaction.atomic():
            action = SystemIntelligenceActionRequest.objects.select_for_update().get(id=action_id)
            if action.status != SystemIntelligenceActionRequest.STATUS_PENDING:
                raise ActionRequestError(f"Action request is already {action.status}.")
            now = timezone.now()
            apply_action(action, user)
            action.status = SystemIntelligenceActionRequest.STATUS_APPLIED
            action.reviewed_by = user
            action.reviewed_at = now
            action.applied_at = now
            action.error_message = ""
            action.save(
                update_fields=[
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "applied_at",
                    "error_message",
                    "target_pk",
                    "target_repr",
                    "updated_at",
                ]
            )
            return action
    except Exception as exc:
        logger.exception("System intelligence action %s failed during approval", action_id)
        if (
            action is not None
            and action.status == SystemIntelligenceActionRequest.STATUS_PENDING
            and not isinstance(exc, PermissionDenied)
        ):
            mark_action_failed(action.id, user, _safe_error_message(exc))
        raise


def reject_action_request(action_id: str | uuid.UUID, user) -> SystemIntelligenceActionRequest:
    """Reject a pending action request without changing target data."""
    with transaction.atomic():
        action = SystemIntelligenceActionRequest.objects.select_for_update().get(id=action_id)
        if action.status != SystemIntelligenceActionRequest.STATUS_PENDING:
            raise ActionRequestError(f"Action request is already {action.status}.")
        action.status = SystemIntelligenceActionRequest.STATUS_REJECTED
        action.reviewed_by = user
        action.reviewed_at = timezone.now()
        action.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        return action


def mark_action_failed(action_id: str | uuid.UUID, user, error_message: str) -> None:
    now = timezone.now()
    SystemIntelligenceActionRequest.objects.filter(
        id=action_id,
        status=SystemIntelligenceActionRequest.STATUS_PENDING,
    ).update(
        status=SystemIntelligenceActionRequest.STATUS_FAILED,
        reviewed_by_id=getattr(user, "pk", None),
        reviewed_at=now,
        error_message=_sanitize_persisted_message(error_message),
        updated_at=now,
    )


def _safe_error_message(exc: BaseException) -> str:
    """Return a vetted message string for persisted error_message fields.

    Pass through messages from exceptions we author (ActionRequestError) or
    from Django framework exceptions whose messages are user-facing
    (PermissionDenied, ValidationError). Replace anything else with a
    generic message; the full traceback is captured via logger.exception.
    """
    if isinstance(exc, ActionRequestError | PermissionDenied | ValidationError):
        return _sanitize_persisted_message(str(exc))
    return _GENERIC_FAILURE_MESSAGE


def _sanitize_persisted_message(message: str) -> str:
    if not isinstance(message, str):
        return _GENERIC_FAILURE_MESSAGE
    cleaned = _CONTROL_CHAR_RE.sub(" ", message).strip()
    return cleaned[:_ERROR_MESSAGE_MAX_LEN] or _GENERIC_FAILURE_MESSAGE


def apply_action(action: SystemIntelligenceActionRequest, user) -> None:
    if action.action_type == SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE:
        check_model_permission(user, CMSPage, "change" if action.target_pk else "add")
        apply_cms_page_update(action)
        return
    model = resolve_model(action.target_app_label, action.target_model, write=True)
    if action.action_type == SystemIntelligenceActionRequest.ACTION_DB_CREATE:
        check_model_permission(user, model, "add")
        apply_db_create(action, model)
    elif action.action_type == SystemIntelligenceActionRequest.ACTION_DB_UPDATE:
        check_model_permission(user, model, "change")
        apply_db_update(action, model)
    elif action.action_type == SystemIntelligenceActionRequest.ACTION_DB_DELETE:
        check_model_permission(user, model, "delete")
        apply_db_delete(action, model)
    else:
        raise ActionRequestError(f"Unsupported action type: {action.action_type}")
