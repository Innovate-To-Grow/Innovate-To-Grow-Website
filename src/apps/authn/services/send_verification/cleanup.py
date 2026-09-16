from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.authn.models import SendVerificationChallenge, SendVerificationRequest

from .config import load_settings
from .metrics import emit


def cleanup_expired_records(*, now=None) -> dict[str, int]:
    config = load_settings()
    now = now or timezone.now()
    expired_challenges = SendVerificationChallenge.objects.filter(
        status=SendVerificationChallenge.Status.PENDING,
        expires_at__lte=now,
    ).update(status=SendVerificationChallenge.Status.EXPIRED, updated_at=now)
    cutoff = now - timedelta(days=config.retention_days)
    deleted_challenges, _ = SendVerificationChallenge.objects.filter(expires_at__lt=cutoff).delete()
    deleted_requests, _ = SendVerificationRequest.objects.filter(idempotency_expires_at__lt=cutoff).delete()
    emit(
        "cleanup",
        expired_challenges=expired_challenges,
        deleted_challenges=deleted_challenges,
        deleted_requests=deleted_requests,
    )
    return {
        "expired_challenges": expired_challenges,
        "deleted_challenges": deleted_challenges,
        "deleted_requests": deleted_requests,
    }
