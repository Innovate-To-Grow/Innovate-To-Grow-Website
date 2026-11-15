"""The in-process campaign runner, used while background jobs are off: one thread sends every recipient in turn.

It runs in the dedicated wait mode, so each message waits for its bulk-lane slot (up to ``waits.dedicated_seconds``).
A recipient the provider throttles (or otherwise holds back for now) is sent again once the cooldown ends, never
failed for it. When the delivery limits hold mail back for longer (a daily budget, a provider stop), the rest of
the recipients are paused and the campaign ends partial; "Resume paused recipients" sends them later.
"""

import logging

from apps.core.models import EmailServiceConfig
from apps.core.services.delivery_rates import WaitMode, wait_mode
from apps.core.services.delivery_rates.rules.defaults import section
from apps.mail.models import RecipientLog
from apps.mail.services.suppression import is_suppressed

from ..audience import get_recipients
from ..campaign.errors import unexpected_delivery_error_message
from ..campaign.personalize import personalize
from ..campaign.preview import render_email_html
from .progress import (
    _fail_campaign_for_missing_delivery_config,
    _finalize_campaign,
    _mark_campaign_sending,
    _refresh_campaign_progress,
)
from .recipient_logs import _configured_provider, _record_send_result, pause_recipients, skip_suppressed_log
from .recipients import _recipient_context, _unsubscribe_url_for, carries_login_link
from .transport import SesSendResult, _get_configuration_set_name, _get_ses_client, _send_via_ses

logger = logging.getLogger(__name__)


def send_campaign(campaign, sent_by):
    recipients = get_recipients(campaign)
    _mark_campaign_sending(campaign, sent_by, len(recipients))
    logs = RecipientLog.objects.bulk_create(
        [
            RecipientLog(
                campaign=campaign,
                member_id=recipient["member_id"],
                email_address=recipient["email"],
                recipient_name=recipient["full_name"],
                attempts=1,
            )
            for recipient in recipients
        ]
    )
    if not recipients:
        return _finalize_campaign(campaign)

    delivery = _load_delivery()
    if delivery[1] is None:
        _fail_campaign_for_missing_delivery_config(campaign, recipients)
    if delivery[0].provider == "ses" and not delivery[2]:
        logger.warning(
            "No SES configuration set configured; bounce/complaint tracking disabled for campaign %s",
            campaign.pk,
        )
    send_to_recipients(campaign, list(zip(recipients, logs, strict=True)), delivery)
    return _finalize_campaign(campaign)


def _load_delivery():
    """``(config, provider config or None, SES configuration set)`` as configured right now."""
    config = EmailServiceConfig.load()
    return config, _get_ses_client(config), _get_configuration_set_name(config)


def send_to_recipients(campaign, pending, delivery=None) -> None:
    """Send each ``(recipient, log)`` on the bulk lane in turn; pause the rest when the delivery limits hold them back.

    The email configuration is re-read every ``jobs.runner_refresh_recipients`` recipients, so a provider change
    made while a long campaign runs applies to the remaining recipients.
    """
    refresh_every = section("jobs")["runner_refresh_recipients"]
    delivery = delivery or _load_delivery()
    # Every admission in this thread may wait up to the dedicated cap for its slot instead of being deferred.
    with wait_mode(WaitMode.DEDICATED):
        for index, (recipient, log) in enumerate(pending, start=1):
            if not _send_one_recipient(campaign, *delivery, recipient, log=log):
                pause_recipients([held for _recipient, held in pending[index - 1 :]])
                break
            if index % refresh_every == 0:
                _refresh_campaign_progress(campaign)
                delivery = _load_delivery()


def _send_one_recipient(campaign, config, ses_client, configuration_set, recipient, *, log=None) -> bool:
    """Send to one recipient and record the outcome; False when the delivery limits held it back (left pending)."""
    try:
        if log is None:
            log = RecipientLog.objects.create(
                campaign=campaign,
                member_id=recipient["member_id"],
                email_address=recipient["email"],
                recipient_name=recipient["full_name"],
                attempts=1,
            )
        if is_suppressed(recipient["email"]):
            # Suppressed after the audience was resolved (a long campaign, or a resumed one): never sent.
            if skip_suppressed_log(log):
                campaign.failed_count += 1
            return True
        context = _recipient_context(recipient, campaign)
        subject = personalize(campaign.subject, context)
        body_html = personalize(campaign.body, context)
        unsubscribe_url = _unsubscribe_url_for(campaign, recipient)
        wrapped_html = render_email_html(body_html, unsubscribe_url=unsubscribe_url)
        result = _send_when_taken(
            lambda: _send_with_configured_provider(
                config=config,
                ses_client=ses_client,
                configuration_set=configuration_set,
                recipient=recipient["email"],
                subject=subject,
                wrapped_html=wrapped_html,
                unsubscribe_url=unsubscribe_url,
                recipient_log_id=log.pk,
                delivery_attempt=log.attempts,
                keep_sent_copy=not carries_login_link(context, subject, body_html),
                campaign_id=campaign.pk,
            )
        )
        if result is None:
            return False
        _record_send_result(campaign, log, result)
    except Exception as exc:
        logger.exception("Failed to process recipient %s", recipient["email"])
        RecipientLog.objects.filter(
            campaign=campaign,
            email_address=recipient["email"],
            status="pending",
        ).update(
            status="failed",
            provider=_configured_provider(config),
            error_message=unexpected_delivery_error_message(exc),
        )
        campaign.failed_count += 1
    return True


def _send_when_taken(send) -> SesSendResult | None:
    """Send one message (``send()``); None when the delivery limits hold it back longer than this thread may wait.

    A provider answer that took nothing but may later (``SesSendResult.held_back``: a throttle, a pause, a used-up
    quota) sends it again: the next admission waits out the cooldown that answer set. Throttles in a row open the
    channel's breaker after ``controller.persistent_throttle_count``, so this stops after as many tries and leaves
    the recipient for "Resume paused recipients".
    """
    for _attempt in range(section("controller")["persistent_throttle_count"]):
        result = send()
        if result.deferred_until is not None:
            return None
        if not result.held_back:
            return result
        logger.info("The email provider held back a campaign message; sending it again after the cooldown.")
    return None


def _send_with_configured_provider(
    *,
    config,
    ses_client,
    configuration_set,
    recipient,
    subject,
    wrapped_html,
    unsubscribe_url,
    recipient_log_id=None,
    delivery_attempt=0,
    keep_sent_copy=True,
    campaign_id=None,
):
    if ses_client is not None:
        return _send_via_ses(
            ses_client=ses_client,
            source=config.source_address,
            recipient=recipient,
            subject=subject,
            html_body=wrapped_html,
            unsubscribe_url=unsubscribe_url,
            configuration_set=configuration_set,
            recipient_log_id=recipient_log_id,
            delivery_attempt=delivery_attempt,
            keep_sent_copy=keep_sent_copy,
            campaign_id=campaign_id,
        )
    return SesSendResult(provider="", error="Email delivery is not configured.")
