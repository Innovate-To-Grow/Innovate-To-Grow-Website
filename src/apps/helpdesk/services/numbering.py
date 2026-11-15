"""Ticket numbers (``I2G-#1234``) and the subject token that names one.

On PostgreSQL numbers come from the sequence ``helpdesk_ticket_number_seq`` (created by ``helpdesk/0001``, starting
at 1001): ``nextval`` is unique under concurrent creation, and a number taken by a rolled-back transaction is simply
skipped. Other databases (SQLite for local development and tests) take the highest number plus one; a race there
hits the unique constraint, and ``create_ticket`` takes the next number and tries again.
"""

import re

from django.db import IntegrityError, connection, transaction
from django.db.models import Max

from ..models import TICKET_PREFIX, Ticket

FIRST_NUMBER = 1001
SEQUENCE = "helpdesk_ticket_number_seq"
_NEXTVAL_SQL = "SELECT nextval('helpdesk_ticket_number_seq')"
# "[I2G-#1234]", also without the brackets, in any letter case; only a hint (the participant check decides).
TOKEN_RE = re.compile(r"\bI2G-#(\d{1,9})\b", re.IGNORECASE)
_CREATE_ATTEMPTS = 5


def next_number() -> int:
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(_NEXTVAL_SQL)
            return int(cursor.fetchone()[0])
    highest = Ticket.objects.aggregate(highest=Max("number"))["highest"]
    return max(FIRST_NUMBER, (highest or 0) + 1)


def create_ticket(**values) -> Ticket:
    """A new ticket with the next free number (call inside a transaction to keep it with its first message)."""
    for _attempt in range(_CREATE_ATTEMPTS - 1):
        try:
            with transaction.atomic():
                return Ticket.objects.create(number=next_number(), **values)
        except IntegrityError:
            continue
    with transaction.atomic():
        return Ticket.objects.create(number=next_number(), **values)


def display(number: int) -> str:
    return f"{TICKET_PREFIX}{number}"


def subject_numbers(subject: str) -> list[int]:
    """The ticket numbers a subject names with the token, in order, unique."""
    return list(dict.fromkeys(int(found) for found in TOKEN_RE.findall(str(subject or ""))))


def parse_number(value) -> int | None:
    """A ticket number typed by staff: "1234", "#1234", "I2G-#1234" or "[I2G-#1234]"; None when it is none."""
    digits = re.fullmatch(r"\s*\[?\s*(?:I2G-)?#?\s*(\d{1,9})\s*\]?\s*", str(value or ""), re.IGNORECASE)
    return int(digits.group(1)) if digits else None
