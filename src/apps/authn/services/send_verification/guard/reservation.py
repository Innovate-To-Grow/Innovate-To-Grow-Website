"""Spending a send's challenge and reserving its destination (and SMS) quotas, and the proof-less observe mode."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.authn.models import SendVerificationChallenge, SendVerificationRequest

from ..rules.config import load_settings
from ..rules.exceptions import SendVerificationConsumed
from .quotas import reserve_send_quotas
from .requests import ProtectedSend


def _mark_consumed(challenge, *, now) -> None:
    """Conditionally move the locked challenge from pending to consumed; it can be spent only once."""
    updated = SendVerificationChallenge.objects.filter(
        pk=challenge.pk,
        status=SendVerificationChallenge.Status.PENDING,
        expires_at__gt=now,
    ).update(
        status=SendVerificationChallenge.Status.CONSUMED,
        consumed_at=now,
        updated_at=now,
    )
    if not updated:
        raise SendVerificationConsumed()


def _reserve_for(record, *, config, now, refuse_spent_sms_budget) -> None:
    """Reserve the destination (and SMS) quotas for a new request and mark it reserved."""
    reserve_send_quotas(
        config=config,
        channel=record.channel,
        destination_kind=record.destination_kind,
        destination_normalized=record.destination_normalized,
        now=now,
        refuse_spent_sms_budget=refuse_spent_sms_budget,
    )
    record.quota_reserved = True
    record.reserved_at = now
    record.save(update_fields=["quota_reserved", "reserved_at", "updated_at"])


def _observe_without_proof(
    *,
    operation,
    destination_kind,
    destination_normalized,
    fingerprint,
    channel,
    principal_type,
    principal_key,
    refuse_spent_sms_budget=False,
) -> ProtectedSend:
    from uuid import uuid4

    config = load_settings()
    now = timezone.now()
    with transaction.atomic():
        reserve_send_quotas(
            config=config,
            channel=channel,
            destination_kind=destination_kind,
            destination_normalized=destination_normalized,
            now=now,
            refuse_spent_sms_budget=refuse_spent_sms_budget,
        )
        record = SendVerificationRequest.objects.create(
            request_id=uuid4(),
            operation=operation,
            channel=channel,
            destination_kind=destination_kind,
            destination_normalized=destination_normalized,
            principal_type=principal_type,
            principal_key=principal_key,
            request_fingerprint=fingerprint,
            status=SendVerificationRequest.Status.PENDING,
            quota_reserved=True,
            reserved_at=now,
            idempotency_expires_at=now + timedelta(seconds=config.idempotency_ttl_seconds),
        )
    return ProtectedSend(record=record, is_replay=False)
