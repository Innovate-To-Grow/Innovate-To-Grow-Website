"""The helpdesk's intake, per mailbox: its own scan of the Inbox, separate from bounce processing.

The intake lists the Graph mailbox's Inbox on its own schedule and records every message in ``core``'s inbound queue,
which the ingest turns into tickets. This row holds that scan's checkpoint, lease and health, and what staff set on
the intake card (Helpdesk → Settings): pause, the first-scan lookback, and the earlier checkpoint a "Rescan since"
moves to. Bounce processing keeps its own row (``core.EmailMonitorState``), so pausing or rescanning one never moves
the other. There is no change form for this row on purpose: a form saves every column and would overwrite a running
scan's lease; each control on the card changes its own columns, under the lease rule (``services.intake.state``).
"""

from django.db import models

from apps.core.models import ProjectControlModel


class IntakeState(ProjectControlModel):
    mailbox = models.CharField(max_length=254, unique=True)
    paused = models.BooleanField(
        default=False,
        help_text="Paused on the intake card: the helpdesk neither lists this mailbox nor imports its mail.",
    )
    checkpoint_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Received time of the newest message every intake scan before it recorded, or the earlier time "
        "staff chose with Rescan since.",
    )
    initial_lookback_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many hours back the first intake scan reads while there is no checkpoint (set on the intake "
        "card). Empty: the EMAIL_MONITORING default.",
    )
    lease_token = models.UUIDField(null=True, blank=True, editable=False)
    lease_until = models.DateTimeField(null=True, blank=True, editable=False)
    last_run_started_at = models.DateTimeField(null=True, blank=True)
    last_run_finished_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    consecutive_failures = models.PositiveIntegerField(default=0)
    next_run_after = models.DateTimeField(null=True, blank=True)
    last_run_stats = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Intake State"
        verbose_name_plural = "Intake States"

    def __str__(self):
        return f"Helpdesk intake for {self.mailbox}"
