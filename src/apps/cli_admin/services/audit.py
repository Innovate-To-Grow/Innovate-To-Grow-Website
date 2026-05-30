from ..models import CliAuditLog


def write_audit(
    *,
    actor,
    action,
    status,
    app_label,
    model_name,
    target_pk="",
    target_repr="",
    changes=None,
    before_snapshot=None,
    cascade=None,
    error_message="",
    request_ip=None,
):
    """Record one CLI write attempt.

    ``changes``/``before_snapshot`` only carry safe-ORM output, which is filtered
    by the field-NAME denylist (password/secret/token/...). That removes obviously
    sensitive fields, but a secret stored in an unrecognized field name or inside a
    JSON/text value is not value-scrubbed — treat audit rows as least-privilege data.
    """
    return CliAuditLog.objects.create(
        actor=actor,
        action=action,
        status=status,
        app_label=app_label,
        model_name=model_name,
        target_pk=str(target_pk or ""),
        target_repr=(target_repr or "")[:300],
        changes=changes or {},
        before_snapshot=before_snapshot or {},
        cascade=cascade or {},
        error_message=error_message or "",
        request_ip=request_ip,
    )
