from django.conf import settings
from django.db import models

from apps.core.models import ProjectControlModel


class CliAuditLog(ProjectControlModel):
    """Append-only audit trail of every CLI admin-API write attempt.

    Payloads cannot leak secrets: ``changes`` only holds denylist-filtered
    ``validate_write_payload`` output and ``before_snapshot`` only denylist-filtered
    ``serialize_model_instance(write=True)`` output.
    """

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    app_label = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    target_pk = models.CharField(max_length=255, blank=True, default="")
    target_repr = models.CharField(max_length=300, blank=True, default="")
    changes = models.JSONField(default=dict, blank=True)
    before_snapshot = models.JSONField(default=dict, blank=True)
    cascade = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    request_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} {self.app_label}.{self.model_name} — {self.get_status_display()}"
