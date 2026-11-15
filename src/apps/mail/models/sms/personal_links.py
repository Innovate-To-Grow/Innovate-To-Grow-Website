"""Personal SMS sign-in links and SMS Settings.

Turning personal sign-in links off (the switch, or links in SMS) revokes them for good. Every write to the row, a
save or a bulk ``update()``, locks it and ends in ``settle_personal_links`` in the same transaction: unless personal
sign-in links were on before and are still on, ``personal_links_epoch`` moves on and every outstanding personal link
is revoked, with a ``SmsLinkRevocation`` for the audit. A personal link carries the epoch it was issued in and signs
in only while that is still the epoch, so it can't come back: not when the switch is turned on again, not when its
own row is edited, and not when it was being issued while the switch went off.
"""

import logging
import uuid
from typing import NamedTuple

from django.db import DEFAULT_DB_ALIAS, transaction
from django.db.models import Max
from django.utils import timezone

from .links import SmsLinkRevocation, SmsLinkToken

logger = logging.getLogger(__name__)

SETTINGS_PK = uuid.UUID("00000000-0000-4000-8000-000000005301")
STATE_FIELDS = ("links_enabled", "personal_links_enabled", "personal_links_epoch")


class PersonalLinkState(NamedTuple):
    """SMS Settings as personal sign-in links see them: both switches, and the epoch a link must carry."""

    links_enabled: bool
    personal_links_enabled: bool
    epoch: int

    @property
    def on(self) -> bool:
        return bool(self.links_enabled and self.personal_links_enabled)


class Settled(NamedTuple):
    epoch: int
    revocation: SmsLinkRevocation | None = None


def locked_state(using=DEFAULT_DB_ALIAS) -> PersonalLinkState | None:
    """The switches and the epoch, locking the row until the caller's transaction ends (None while there is no row)."""
    from .config import SmsConfig  # config imports this module

    rows = SmsConfig._base_manager.db_manager(using).select_for_update().filter(pk=SETTINGS_PK)
    row = rows.values_list(*STATE_FIELDS).first()
    return PersonalLinkState(*row) if row else None


def revoke_personal_links(*, actor=None, via, using=DEFAULT_DB_ALIAS) -> Settled:
    """Settle personal sign-in links as they stand, without a write: what to do on finding links still live while
    they are off (turned off outside the app, by raw SQL)."""
    with transaction.atomic(using=using):
        return settle_personal_links(locked_state(using), actor=actor, via=via, using=using)


def settle_personal_links(before: PersonalLinkState | None, *, actor=None, via, using=DEFAULT_DB_ALIAS) -> Settled:
    """Run in the transaction of a write to SMS Settings, after it, with the row still locked; ``before`` is how the
    row stood before the write. Unless personal sign-in links were on before and are still on, the epoch moves on,
    so no personal link issued earlier ever signs in again, and every outstanding one is revoked. The revocation is
    recorded when the write turned them off, or when it found links still live while they were off."""
    after = locked_state(using)
    if after is None:  # No row (a bulk update that matched none, the row deleted): nothing to settle.
        return Settled(before.epoch if before is not None else 0)
    if before is not None and before.on and after.on:
        if after.epoch < before.epoch:  # A bulk update must not move the epoch back either.
            _set_epoch(before.epoch, using)
        return Settled(max(before.epoch, after.epoch))
    floor = before.epoch if before is not None else _highest_issued_epoch(using)
    epoch = max(floor, after.epoch) + 1
    _set_epoch(epoch, using)
    revoked = _revoke_outstanding(before, using)
    reason = _revocation_reason(before, after, revoked)
    if reason is None:
        return Settled(epoch)
    revocation = SmsLinkRevocation.objects.using(using).create(
        reason=reason, via=via, actor=actor, actor_label=_who(actor), revoked_count=revoked, epoch=epoch
    )
    # Links found live while off mean the switch was changed outside the app: worth a warning.
    log = logger.warning if reason == SmsLinkRevocation.Reason.FOUND_OFF else logger.info
    log("Revoked %d personal SMS sign-in link(s): %s (%s); epoch now %d.", revoked, reason, via, epoch)
    return Settled(epoch, revocation)


def _revoke_outstanding(before: PersonalLinkState | None, using) -> int:
    """Revoke every outstanding personal link; the number that still worked until now (issued in the epoch that was
    current). One from an earlier epoch (stored while a switch-off committed) never worked: tidied, not counted."""
    now = timezone.now()
    values = {"revoked_at": now, "expires_at": now, "updated_at": now}
    outstanding = SmsLinkToken.objects.using(using).outstanding_personal()
    if before is None:  # No row to say which epoch was current: count them all.
        return outstanding.update(**values)
    revoked = outstanding.filter(epoch=before.epoch).update(**values)
    outstanding.update(**values)
    return revoked


def _revocation_reason(before: PersonalLinkState | None, after: PersonalLinkState, revoked: int) -> str | None:
    if before is not None and before.on:
        if not after.personal_links_enabled:
            return SmsLinkRevocation.Reason.PERSONAL_LINKS_OFF
        return SmsLinkRevocation.Reason.LINKS_OFF
    # They were already off, yet links were still live: they were turned off without going through a write here.
    return SmsLinkRevocation.Reason.FOUND_OFF if revoked else None


def _set_epoch(epoch: int, using) -> None:
    from .config import SmsConfig  # config imports this module

    SmsConfig._base_manager.db_manager(using).filter(pk=SETTINGS_PK).update(personal_links_epoch=epoch)


def _highest_issued_epoch(using) -> int:
    # The row is new (or was deleted): start past every link ever issued, so none can match it again.
    return SmsLinkToken.objects.using(using).aggregate(top=Max("epoch"))["top"] or 0


def _who(actor) -> str:
    if actor is None:
        return ""
    name, email = actor.get_full_name(), actor.get_primary_email()
    return (f"{name} <{email}>" if name and email else name or email or str(actor.pk))[:255]
