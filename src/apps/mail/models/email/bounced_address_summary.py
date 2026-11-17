"""What the Bounced addresses list shows about an address: its counts by category, the latest category's label and
guidance, and the resolution."""

from apps.core.models import EmailBounce

from .bounce_records import BouncedAddressAction

Category = EmailBounce.Category
# The categories that count toward "repeated temporary failures" (with SES transient and undetermined bounces).
TEMPORARY_CATEGORIES = (Category.TRANSIENT, Category.MAILBOX_FULL, Category.UNKNOWN)
# Short labels for the counts column, in the order shown.
CATEGORY_SHORT_LABELS = {
    Category.HARD: "not found",
    Category.MAILBOX_DISABLED: "disabled",
    Category.MAILBOX_FULL: "full",
    Category.TRANSIENT: "temporary",
    Category.SPAM_REJECTED: "spam / reputation",
    Category.RELAY_DENIED: "relay denied",
    Category.POLICY_REJECTED: "policy",
    Category.DELAYED: "delayed",
    Category.UNKNOWN: "unknown",
}


class BouncedAddressSummaryMixin:
    """Count and label properties for ``BouncedAddress``."""

    @property
    def is_suppressed(self) -> bool:
        return self.suppressed_at is not None

    @property
    def hard_total(self) -> int:
        return self.hard_count + self.ses_permanent_count

    @property
    def soft_total(self) -> int:
        return self.soft_count + self.ses_transient_count

    @property
    def unknown_total(self) -> int:
        return self.unknown_count + self.ses_undetermined_count

    def category_count(self, category: str) -> int:
        """How many Microsoft Graph reports of ``category`` were counted."""
        return int((self.category_counts or {}).get(category) or 0)

    @property
    def category_items(self) -> list[dict]:
        """The Graph reports by category, in a fixed order (categories with none left out)."""
        return [
            {"category": category, "label": short, "title": Category(category).label, "count": count}
            for category, short in CATEGORY_SHORT_LABELS.items()
            if (count := self.category_count(category))
        ]

    @property
    def temporary_total(self) -> int:
        """Temporary failures: Graph reports of a temporary, full-mailbox or unknown category, and SES transient and
        undetermined bounces. They only ever count toward "repeated temporary failures"."""
        graph = sum(self.category_count(category) for category in TEMPORARY_CATEGORIES)
        return graph + self.ses_transient_count + self.ses_undetermined_count

    @property
    def last_category_label(self) -> str:
        return dict(Category.choices).get(self.last_category, self.last_category)

    @property
    def last_category_guidance(self) -> str:
        return EmailBounce.guidance_for(self.last_category)

    @property
    def last_category_hint(self) -> str:
        return EmailBounce.hint_for(self.last_category)

    @property
    def suggests_address_action(self) -> bool:
        """Whether the suggestion is about the address itself (not our sending side or the recipient's policy)."""
        return self.suggestion in self.ADDRESS_SUGGESTIONS

    @property
    def has_matched_evidence(self) -> bool:
        """Whether a report or notice matched an email the site sent, or an Amazon SES event (signed by AWS) names the
        address."""
        return bool(
            self.matched_count
            or self.left_org_count
            or self.ses_permanent_count
            or self.ses_transient_count
            or self.ses_undetermined_count
            or self.complaint_count
        )

    @property
    def left_org_contact_label(self) -> str:
        return self.CONTACT_KINDS.get(self.left_org_contact_kind, "an address the notice names")

    @property
    def left_org_has_contact_hint(self) -> bool:
        return bool(self.left_org_contact or self.left_org_contact_name or self.left_org_contact_phone)

    @property
    def graph_is_latest(self) -> bool:
        """Whether the latest event is a Microsoft Graph report (else an SES event, or nothing)."""
        if self.graph_last_at is None or not self.last_classification:
            return False
        return self.ses_last_at is None or self.graph_last_at >= self.ses_last_at

    @property
    def resolution_label(self) -> str:
        return dict(BouncedAddressAction.Action.choices).get(self.resolution, self.resolution)

    @property
    def report_total(self) -> int:
        """Every bounce and delay report and SES event counted for the address (complaints included)."""
        return (
            self.hard_total
            + self.soft_total
            + self.unknown_total
            + self.rejected_count
            + self.delayed_count
            + self.complaint_count
        )
