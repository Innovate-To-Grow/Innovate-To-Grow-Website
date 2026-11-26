from ....services.members.import_.review.analysis.describe import PRECEDENCE, conflict_code, conflict_title

CHOICE_WORDS = {
    "create": "create",
    "update": "update",
    "update_make_primary": "update and make primary",
    "update_same_person": "same person, with the name",
    "update_keep_name": "same person, keep the name",
    "use_member": "use a member",
    "use_row": "use this row",
    "ignore_uuid": "match by email",
    "create_claim": "create a member with the address",
    "attach_to": "attach to a member",
    "skip": "skip",
}


# By the keys applied batches keep in their summary: a key never changes, only its title.
LISTED_TITLES = {
    "privileged_changes": "Changes to Admin accounts",
    "verified": "Email addresses marked verified (each becomes a sign-in factor)",
    "emails_deleted": "Contact emails deleted",
    "phones_deleted": "Phone numbers deleted",
    "resubscribed": "Re-subscribed",
    "unverified": "Email addresses marked unverified",
    "active_changes": "Members deactivated or reactivated",
    # Imports no longer change Admin access; kept for the result pages of imports applied before.
    "staff_changes": "Admin access granted or removed",
    "primary_changes": "Primary email changes",
}


def confirm_lines(summary: dict) -> dict:
    """The confirm page's decision counts and spelled-out risky changes, in words."""
    decisions = [
        {
            "code": conflict_code(conflict),
            "title": conflict_title(conflict),
            "counts": ", ".join(f"{count} {CHOICE_WORDS.get(choice, choice)}" for choice, count in choices.items()),
        }
        for conflict in PRECEDENCE
        if (choices := summary["decisions"].get(conflict))
    ]
    listed = [
        {"title": title, "items": summary["listed"][kind]}
        for kind, title in LISTED_TITLES.items()
        if summary["listed"].get(kind)
    ]
    return {"decision_lines": decisions, "listed_lines": listed, "rows_summary": summary["rows"]}


def risky_lines(risky: dict) -> list[dict]:
    """The result page's counts of risky changes, titled as on the confirm page."""
    return [{"title": title, "count": risky[kind]} for kind, title in LISTED_TITLES.items() if risky.get(kind)]
