"""One Message Trace sync's work: day-long windows of the sender's trace, read within the run's request budget, and
the delivery statuses written from them.

Each window starts just before the oldest-checked candidate (an accepted Graph email still unknown, without bounce
or delayed, old enough to be in the trace and not yet given up on), so every candidate is reached in turn. Writes are
guarded single-row updates: a stronger status (``DeliveryStatus.stronger_than``), such as a bounce's confirmed
failure saved meanwhile, is never replaced. Every candidate of a window read is stamped ``trace_checked_at``.

A window whose pages outran the request budget was read only in part (no inference from it, and the same first pages
would be read again), so the next window is half as long, an hour at least; once every window fits with room to
spare, the length doubles back up to a day. The length is carried to the next run in its stats (``window_minutes``).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db.models import F, Q

from apps.core.models import EmailCategory, OutboundEmail

from . import limits, matching
from .reader import MAX_WINDOW, GraphTraceReader

DeliveryStatus = OutboundEmail.DeliveryStatus
CANDIDATE_STATUSES = (DeliveryStatus.UNKNOWN, DeliveryStatus.NO_BOUNCE, DeliveryStatus.DELAYED)
# Most emails one window evaluates, and most it compares them with (a fuller window is not used for inference).
MAX_CANDIDATES = 2000
MAX_PEERS = 10000
MIN_WINDOW = timedelta(hours=1)
_FIELDS = ("id", "recipient", "recipients", "subject_digest", "internet_message_id", "accepted_at", "last_attempt_at")
STAT_KEYS = (
    "requests",
    "windows",
    "incomplete",
    "rows",
    "checked",
    "updated",
    "pending",
    "delivered",
    "failed",
    "junk",
)


@dataclass
class TraceRun:
    reader: GraphTraceReader
    mailbox: str
    now: datetime
    budget: int
    span: timedelta = MAX_WINDOW
    stats: dict = field(default_factory=lambda: dict.fromkeys(STAT_KEYS, 0))
    widest: int = 0  # most pages one complete window needed this run

    def __post_init__(self):
        self.resize(self.span)

    def resize(self, span: timedelta) -> None:
        self.span = max(MIN_WINDOW, min(span, MAX_WINDOW))
        self.stats["window_minutes"] = int(self.span.total_seconds() // 60)

    def candidates(self):
        newest = self.now - max(timedelta(minutes=limits.min_age_minutes()), matching.LATEST)
        return OutboundEmail.objects.filter(
            provider="graph",
            mailbox=self.mailbox,
            status=OutboundEmail.Status.ACCEPTED,
            delivery_status__in=CANDIDATE_STATUSES,
            accepted_at__gte=self.now - timedelta(hours=limits.give_up_hours()),
            accepted_at__lte=newest,
        ).exclude(category=EmailCategory.ACCESS_CHECK)

    def execute(self) -> str:
        """``ok`` when every candidate's window was read in full this run, ``partial`` when the request budget ran out
        first (the candidates of a partly read window are still stamped, so the next run starts with others)."""
        while True:
            first = (
                self.candidates()
                .filter(Q(trace_checked_at__isnull=True) | Q(trace_checked_at__lt=self.now))
                .order_by(F("trace_checked_at").asc(nulls_first=True), "accepted_at")
                .only("accepted_at")
                .first()
            )
            if first is None:
                if not self.stats["incomplete"] and self.widest and self.widest * 2 <= max(self.budget, 2):
                    self.resize(self.span * 2)
                return "partial" if self.stats["incomplete"] else "ok"
            if self.stats["requests"] >= self.budget:
                return "partial"
            self.window(first.accepted_at - matching.EARLIEST)

    def window(self, start: datetime) -> None:
        end = min(start + self.span, self.now)
        rows, complete, skiptoken, pages = [], False, "", 0
        while self.stats["requests"] < self.budget:
            self.stats["requests"] += 1
            pages += 1
            page = self.reader.page(start, end, skiptoken=skiptoken)
            rows.extend(matching.parse_rows(page.rows))
            skiptoken = page.skiptoken
            if not skiptoken:
                complete = True
                break
        self.stats["windows"] += 1
        self.stats["rows"] += len(rows)
        lowest, highest = start + matching.EARLIEST, end - matching.LATEST
        candidates = list(
            self.candidates().filter(accepted_at__range=(lowest, highest)).order_by("accepted_at")[:MAX_CANDIDATES]
        )
        sent = Q(accepted_at__range=(start - matching.LATEST, end + matching.EARLIEST)) | Q(
            accepted_at__isnull=True,
            status=OutboundEmail.Status.UNCERTAIN,
            last_attempt_at__range=(start - matching.LATEST, end + matching.EARLIEST),
        )
        peers = (
            list(OutboundEmail.objects.filter(sent, provider="graph").only(*_FIELDS)[: MAX_PEERS + 1]) if rows else []
        )
        complete = complete and len(peers) <= MAX_PEERS
        if complete:
            self.widest = max(self.widest, pages)
        else:
            self.stats["incomplete"] += 1
            self.resize(self.span / 2)
        found = matching.match_rows(peers if complete else candidates, rows, complete=complete) if rows else {}
        for email in candidates:
            if email.pk in found:
                self.write(email, found[email.pk][1])
        checked = OutboundEmail.objects.filter(pk__in=[email.pk for email in candidates])
        self.stats["checked"] += checked.update(trace_checked_at=self.now)

    def write(self, email: OutboundEmail, verdict: matching.Verdict) -> None:
        row = OutboundEmail.objects.filter(pk=email.pk, status=OutboundEmail.Status.ACCEPTED)
        trace = {"trace_status": verdict.trace_status, "trace_checked_at": self.now, "updated_at": self.now}
        new = verdict.delivery_status
        if new is None:
            self.stats["pending"] += 1
            row.update(**trace)
            return
        guarded = row.exclude(delivery_status__in=[*DeliveryStatus.stronger_than(new), DeliveryStatus.NOT_APPLICABLE])
        if guarded.update(delivery_status=new, **trace):
            self.stats["updated"] += 1
            key = {DeliveryStatus.DELIVERED: "delivered", DeliveryStatus.FAILURE_CONFIRMED: "failed"}.get(new, "junk")
            self.stats[key] += 1
        else:
            row.update(**trace)
