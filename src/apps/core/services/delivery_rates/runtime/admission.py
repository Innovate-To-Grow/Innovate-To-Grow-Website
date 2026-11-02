"""What ``admit`` hands back: an ``Admission`` (the slot taken, to be settled with ``record`` or ``release``), or a
``RateDeferred`` naming when to try again."""

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from ..rules.signals import RateSignal


@dataclass(frozen=True)
class Costs:
    """What one request costs: ``pace`` against the rate (1 per message; SES: recipients), ``budget`` against the
    daily limits (recipients; SMS: messages), and its ``external`` recipients, ``messages`` and SMS ``parts``."""

    pace: float = 1
    budget: int = 0
    external: int = 0
    messages: int = 0
    parts: int | None = None

    def __post_init__(self):
        if self.pace <= 0 or min(self.budget, self.external, self.messages) < 0 or self.external > self.budget:
            raise ValueError("Delivery costs must be positive, and external recipients a part of the budget cost.")
        if self.parts is not None and self.parts < 1:
            raise ValueError("An SMS has at least one part.")

    @property
    def internal(self) -> int:
        return self.budget - self.external

    @property
    def counted(self) -> bool:
        return bool(self.budget or self.messages)


@dataclass(eq=False)
class Admission:
    """One request let through. Settle it exactly once: ``record`` after the provider call, ``release`` when it is
    abandoned before the call (later calls are no-ops)."""

    channel: str
    identity: str
    cooldown_group: str
    lane: str
    state_id: uuid.UUID
    admitted_at: datetime
    send_at: datetime
    mode: str
    costs: Costs
    tat_before: datetime | None
    tat_after: datetime
    tat_bulk_before: datetime | None = None
    tat_bulk_after: datetime | None = None
    bucket_start: datetime | None = None
    # Set when this request is a breaker's probe: its outcome closes or reopens the breaker.
    probe_id: uuid.UUID | None = None
    # ``controlled`` records this signal (default OK) when its block finishes without an exception.
    signal: RateSignal | None = None
    settled: bool = field(default=False)

    @property
    def wait_seconds(self) -> float:
        return max(0.0, (self.send_at - self.admitted_at).total_seconds())


class RateDeferred(Exception):
    """Not admitted: try again at ``until`` (certainly not sent). ``reason`` is a short code such as ``pace``,
    ``cooldown``, ``breaker:auth`` or ``budget:daily``; ``retry_after`` is the wait in whole seconds."""

    def __init__(self, until: datetime, reason: str, *, now: datetime, resume_at: datetime | None = None):
        self.until = until
        self.reason = reason
        self.retry_after = max(0, math.ceil((until - now).total_seconds()))
        # When a caller that may wait longer should try again (for a campaign: one bulk interval before ``until``).
        self.resume_at = resume_at or until
        super().__init__(f"Delivery deferred for about {self.retry_after} s ({reason}).")


class RateRefused(Exception):
    """The request alone costs more than a whole daily limit allows, so waiting can never admit it."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"The request is larger than the delivery limit allows ({reason}).")
