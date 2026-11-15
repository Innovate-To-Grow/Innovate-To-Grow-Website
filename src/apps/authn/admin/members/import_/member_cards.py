from django.urls import NoReverseMatch, reverse

_ROLE_ORDER = {"primary": 0, "secondary": 1, "other": 2}


MATCHED_BY = {"uuid": "Member UUID", "primary": "Primary email", "secondary": "Secondary email", "other": "Other email"}


def _url(name: str, *args) -> str:
    try:
        return reverse(f"admin:{name}", args=args)
    except NoReverseMatch:  # pragma: no cover - every authn admin is registered in this project
        return ""


def member_card(member, *, matched: set[str], matched_by: str = "") -> dict:
    badges = ["Active" if member.is_active else "Inactive"]
    badges += [label for flag, label in ((member.registration_pending, "Unfinished sign-up"),) if flag]
    badges += [label for flag, label in ((member.is_staff, "Staff"), (member.is_superuser, "I2G Master")) if flag]
    emails = sorted(member.emails, key=lambda e: (_ROLE_ORDER.get(e.type, 3), e.address.lower()))
    return {
        "id": member.id,
        "short_id": member.id[:8],
        "name": member.full_name or "Unnamed member",
        "url": _url("authn_member_change", member.id),
        "badges": badges,
        "organization": member.organization,
        "title": member.title,
        "date_joined": member.date_joined[:10],
        "last_login": member.last_login[:10] if member.last_login else "never",
        "matched_by": MATCHED_BY.get(matched_by, ""),
        "emails": [
            {**_contact(e), "address": e.address, "type": e.type, "url": _url("authn_contactemail_change", e.id)}
            | {"matched": e.id in matched}
            for e in emails
        ],
        "phones": [
            {
                **_contact(p),
                "address": p.e164,
                "url": _url("authn_contactphone_change", p.id),
                "matched": p.id in matched,
            }
            for p in member.phones
        ],
    }


def _contact(record) -> dict:
    return {"verified": record.verified, "subscribe": record.subscribe}


def _candidates(analysis, snapshot) -> tuple[list[dict], list[dict]]:
    """Member cards for every member the row's analysis read (its target first), and the unlinked records."""
    values, facts = analysis.values, analysis.facts
    records = [
        *snapshot.email_records(values.get("primary_email")),
        *snapshot.email_records(values.get("secondary_email")),
    ]
    matched = {c.id for c in snapshot.email_records(values.get("primary_email"))}
    order = [facts.get("target"), facts.get("uuid_member"), facts.get("email_member"), *snapshot.members]
    cards = []
    for member_id in dict.fromkeys(m for m in order if m):
        member = snapshot.member(member_id)
        if member is not None:
            how = facts.get("matched_by") if member_id == facts.get("target") else ""
            cards.append(member_card(member, matched=matched, matched_by=how))
    unlinked = [
        {"address": c.address, "created": c.created[:10], **_contact(c), "url": _url("authn_contactemail_change", c.id)}
        for c in dict.fromkeys(records)
        if c.member is None
    ]
    return cards, unlinked
