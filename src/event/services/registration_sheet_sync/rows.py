from event.models import Event, EventRegistration


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
    row = [
        str(order),
        registration.attendee_first_name,
        registration.attendee_last_name,
    ]
    if event.collect_phone:
        row.append(registration.attendee_phone)
    row += [
        registration.created_at.strftime("%Y-%m-%d %H:%M"),
        registration.updated_at.strftime("%Y-%m-%d %H:%M"),
        registration.attendee_email,
    ]
    if event.allow_secondary_email:
        row.append(registration.attendee_secondary_email)
    row.append(registration.ticket.name)
    for question_text in question_texts:
        row.append(answers_map.get(question_text, ""))
    return row
