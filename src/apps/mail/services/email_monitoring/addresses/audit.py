"""The two records every bounced-address action leaves: a ``BouncedAddressAction`` row (append-only, with snapshots
that survive the member's deletion) and a Django admin history line on the affected object (the member when there is
one, so it shows in the member's History; the bounced-address row otherwise)."""

from django.contrib.admin.models import CHANGE, LogEntry

from apps.mail.models import BouncedAddress, BouncedAddressAction

CLASSIFICATION_LABELS = {
    "hard": "hard bounce",
    "soft": "soft bounce",
    "rejected": "rejection",
    "delayed": "delay",
    "unknown": "unknown status",
}


def person_label(member) -> str:
    if member is None:
        return ""
    name = member.get_full_name()
    email = member.get_primary_email()
    if name and email:
        return f"{name} <{email}>"[:255]
    return (name or email or str(member.pk))[:255]


def evidence(row: BouncedAddress) -> str:
    """A short summary of the reports, e.g. "hard bounce 5.1.1, 3 reports"."""
    parts = []
    graph_latest = row.graph_last_at is not None and (row.ses_last_at is None or row.graph_last_at >= row.ses_last_at)
    if graph_latest and row.last_classification:
        label = CLASSIFICATION_LABELS.get(row.last_classification, row.last_classification)
        parts.append(f"{label} {row.last_status_code}")
    elif row.ses_last:
        parts.append(f"SES {row.ses_last.get('event', 'bounce')} {row.ses_last.get('type', '')}")
    total = row.report_total
    parts.append(f"{total} report{'' if total == 1 else 's'}")
    return ", ".join(part.strip() for part in parts if part.strip())


def record(request, target, action: str, *, note: str = "", role_after: str = "", details=None, member=None):
    """Append the action row for ``target`` (a ``guards.Target``)."""
    member = member if member is not None else (target.member or (target.owners[0] if target.owners else None))
    data = dict(details or {})
    if len(target.owners) > 1:
        data.setdefault("members", [str(owner.pk) for owner in target.owners])
    return BouncedAddressAction.objects.create(
        bounced_address=target.row,
        address=target.row.address,
        action=action,
        actor=request.user,
        actor_label=person_label(request.user),
        member=member,
        member_ref=member.pk if member is not None else None,
        member_name=person_label(member),
        role_before=target.role,
        role_after=role_after,
        note=(note or "")[:500],
        details=data,
    )


def history(request, objects, message: str, *, flag=CHANGE) -> None:
    """One admin history line on each object (written before a deletion, so its description survives)."""
    for obj in objects:
        LogEntry.objects.log_actions(
            user_id=request.user.pk,
            queryset=[obj],
            action_flag=flag,
            change_message=f"Bounced addresses: {message}"[:2000],
            single_object=True,
        )


def record_rebuild(request, details: dict) -> BouncedAddressAction:
    """The audit row of a counts rebuild (it concerns every address, so it names none)."""
    return BouncedAddressAction.objects.create(
        action=BouncedAddressAction.Action.REBUILD,
        actor=request.user,
        actor_label=person_label(request.user),
        details=dict(details),
    )
