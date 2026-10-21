"""Campaign delivery through the durable outbox.

``launch`` starts a send (one outbox job per recipient, or the legacy in-process
run); ``email_job`` / ``sms_job`` are the per-recipient handlers registered in
``MailConfig.ready()``; ``job_state`` mirrors outbox state into recipient logs;
``channels`` describes what email and SMS delivery share.
"""

from .channels import aggregate_email_campaign, aggregate_sms_campaign
from .email_job import send_email_recipient_job
from .job_state import prepare_delivery_log_retry, resolve_stale_delivery_job, sync_delivery_job_state
from .launch import dispatch_email_campaign, dispatch_sms_campaign, queue_email_campaign, queue_sms_campaign
from .sms_job import send_sms_recipient_job

__all__ = [
    "aggregate_email_campaign",
    "aggregate_sms_campaign",
    "dispatch_email_campaign",
    "dispatch_sms_campaign",
    "prepare_delivery_log_retry",
    "queue_email_campaign",
    "queue_sms_campaign",
    "resolve_stale_delivery_job",
    "send_email_recipient_job",
    "send_sms_recipient_job",
    "sync_delivery_job_state",
]
