FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def safe_sheet_value(value) -> str:
    text = str(value or "")
    return f"'{text}" if text.startswith(FORMULA_TRIGGERS) else text


def build_header() -> list[str]:
    return [
        "UUID",
        "First Name",
        "Middle Name",
        "Last Name",
        "Primary Email",
        "Primary Phone",
        "Organization",
        "Title",
        "Date Joined (UTC)",
        "Last Updated (UTC)",
        "Active",
    ]


def build_row(member) -> list[str]:
    phones = getattr(member, "_prefetched_objects_cache", {}).get("contact_phones")
    if phones is not None:
        primary_phone = phones[0].phone_number if phones else ""
    else:
        phone_obj = member.contact_phones.first()
        primary_phone = phone_obj.phone_number if phone_obj else ""

    return [
        str(member.id),
        safe_sheet_value(member.first_name),
        safe_sheet_value(member.middle_name),
        safe_sheet_value(member.last_name),
        safe_sheet_value(member.get_primary_email()),
        safe_sheet_value(primary_phone),
        safe_sheet_value(member.organization),
        safe_sheet_value(member.title),
        member.date_joined.strftime("%Y-%m-%d %H:%M"),
        member.updated_at.strftime("%Y-%m-%d %H:%M"),
        "Yes" if member.is_active else "No",
    ]
