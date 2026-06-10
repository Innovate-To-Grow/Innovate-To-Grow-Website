from apps.core.services.sheets_safety import safe_sheet_value
from apps.event.models import Event, EventRegistration


def build_header(event: Event, question_texts: list[str]) -> list[str]:
    header = [
        "Order",
        "First Name",
        "Last Name",
    ]
    if event.collect_phone:
        header.append("Phone")
    header += [
        "When Started",
        "Last Updated",
        "Membership Primary",
    ]
    if event.allow_secondary_email:
        header.append("Membership Secondary")
    header.append("Ticket Type")
    header.extend(question_texts)
    return header


def build_row(
    registration: EventRegistration,
    event: Event,
    question_texts: list[str],
    order: int,
) -> list[str]:
    answers_map = {answer["question_text"]: answer["answer"] for answer in registration.question_answers}
    # Attendee-supplied fields (names, phone, secondary email, free-text answers)
    # are written with value_input_option="USER_ENTERED", so neutralize them to
    # block spreadsheet formula/CSV injection (see safe_sheet_value).
    row = [
        str(order),
        safe_sheet_value(registration.attendee_first_name),
        safe_sheet_value(registration.attendee_last_name),
    ]
    if event.collect_phone:
        row.append(safe_sheet_value(registration.attendee_phone))
    row += [
        registration.created_at.strftime("%Y-%m-%d %H:%M"),
        registration.updated_at.strftime("%Y-%m-%d %H:%M"),
        safe_sheet_value(registration.attendee_email),
    ]
    if event.allow_secondary_email:
        row.append(safe_sheet_value(registration.attendee_secondary_email))
    row.append(safe_sheet_value(registration.ticket.name))
    for question_text in question_texts:
        row.append(safe_sheet_value(answers_map.get(question_text, "")))
    return row
