"""
Audit for the pre-``registration_pending`` self-reactivation path.

Before ``Member.registration_pending`` existed, every inactive member counted as a pending
registration, so an admin-deactivated account could request a REGISTER code and reactivate
itself by verifying it. Admin deactivations leave no log entry, so this audit looks for the
other side instead: REGISTER codes issued to a member that was already active before the code
existed. Read-only.
"""

from __future__ import annotations

from datetime import timedelta
from functools import reduce
from operator import or_

from django.db.models import BooleanField, Exists, ExpressionWrapper, F, OuterRef, Q, QuerySet, Subquery

from apps.authn.models import EmailAuthChallenge

REGISTER = EmailAuthChallenge.Purpose.REGISTER
# Self-service signup creates the member and its first REGISTER code in the same request.
SIGNUP_WINDOW = timedelta(minutes=10)

_EARLIER = {"member_id": OuterRef("member_id"), "created_at__lt": OuterRef("created_at")}


def _flag(condition: Q) -> ExpressionWrapper:
    return ExpressionWrapper(condition, output_field=BooleanField())


# Each entry is evidence that the member was active before this REGISTER code was issued.
_EVIDENCE = {
    # LOGIN / password / contact / event / admin codes are only ever issued to active members.
    "earlier_other_code": Exists(EmailAuthChallenge.objects.filter(**_EARLIER).exclude(purpose=REGISTER)),
    # A consumed REGISTER code activates the account; a later one means it was deactivated in between.
    "earlier_consumed_register": Exists(
        EmailAuthChallenge.objects.filter(**_EARLIER, purpose=REGISTER, status=EmailAuthChallenge.Status.CONSUMED)
    ),
    # Imported / admin-created / phone-signup members get their first REGISTER code long after creation.
    "not_created_by_signup": _flag(Q(first_register_at__gt=F("member__created_at") + SIGNUP_WINDOW)),
    "logged_in_before": _flag(Q(member__last_login__lt=F("created_at"))),
    "staff": _flag(Q(member__is_staff=True) | Q(member__is_superuser=True)),
}
REASONS = tuple(_EVIDENCE)


def find_register_reactivations() -> QuerySet[EmailAuthChallenge]:
    """REGISTER codes issued to an already-active member: consumed ones (reactivations) first, then newest.

    A ``consumed`` row means the account was reactivated; ``pending``/``expired`` rows are attempts
    that never completed. Each row is annotated with one boolean per name in :data:`REASONS`.
    """
    first_register_at = (
        EmailAuthChallenge.objects.filter(member_id=OuterRef("member_id"), purpose=REGISTER)
        .order_by("created_at")
        .values("created_at")[:1]
    )
    return (
        EmailAuthChallenge.objects.filter(purpose=REGISTER)
        .annotate(first_register_at=Subquery(first_register_at))
        .annotate(**_EVIDENCE)
        .filter(reduce(or_, (Q(**{name: True}) for name in REASONS)))
        .select_related("member")
        .order_by("status", "-created_at")  # "consumed" sorts before "expired" and "pending"
    )


def reactivation_reasons(challenge: EmailAuthChallenge) -> list[str]:
    """Names of the evidence annotations that flagged ``challenge``."""
    return [name for name in REASONS if getattr(challenge, name)]
