"""Shared fixtures for the member import review tests: sheets, members, contacts and one-call analysis/apply."""

from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_.reader import read_upload
from apps.authn.services.members.import_.review import (
    analyse_rows,
    create_batch,
    load_snapshot,
    lock_members,
    run_import,
)
from apps.authn.services.members.import_.review.analysis import UPDATE_EXISTING, Context

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADERS = [
    "Primary Email",
    "First Name",
    "Last Name",
    "Primary Verified",
    "Primary Subscribed",
    "Secondary Email",
    "Secondary Verified",
    "Secondary Subscribed",
    "Phone Number",
    "Phone Verified",
    "Phone Subscribed",
    "Active",
    "Staff",
    "Organization",
    "Title",
]


def workbook_bytes(headers, rows, *, sheets=None, active=0) -> bytes:
    """An .xlsx with ``headers`` + ``rows`` on its first sheet (``sheets`` adds ``(title, rows)`` sheets before it)."""
    workbook = Workbook()
    first = workbook.active
    first.title = "Members"
    for row in [headers, *rows]:
        first.append(row)
    for index, (title, extra_rows) in enumerate(sheets or []):
        sheet = workbook.create_sheet(title=title, index=index)
        for row in extra_rows:
            sheet.append(row)
    workbook.active = active
    payload = BytesIO()
    workbook.save(payload)
    return payload.getvalue()


def upload(headers, rows, name="members.xlsx", **kwargs) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, workbook_bytes(headers, rows, **kwargs), content_type=XLSX)


def row(primary, **cells) -> list:
    """One HEADERS row; names default to Ada Lovelace, every other cell to blank."""
    values = {"First Name": "Ada", "Last Name": "Lovelace", **{k.replace("_", " "): v for k, v in cells.items()}}
    return [primary if header == "Primary Email" else values.get(header) for header in HEADERS]


def read(headers, rows):
    return read_upload(BytesIO(workbook_bytes(headers, rows)))


class ImportTestCase(TestCase):
    """A member Ada Lovelace (verified primary ada@example.com) and helpers to add others."""

    def setUp(self):
        cache.clear()
        self.ada = self.member("Ada", "Lovelace", "ada@example.com")

    def tearDown(self):
        cache.clear()

    @staticmethod
    def member(first, last, primary=None, *, verified=True, subscribe=True, **fields):
        member = Member.objects.create_user(password="StrongPass123!", first_name=first, last_name=last, **fields)
        if primary:
            ContactEmail.objects.create(
                member=member, email_address=primary, email_type="primary", verified=verified, subscribe=subscribe
            )
        return member

    @staticmethod
    def email(member, address, email_type="secondary", **flags):
        return ContactEmail.objects.create(member=member, email_address=address, email_type=email_type, **flags)

    @staticmethod
    def phone(member, number, **flags):
        return ContactPhone.objects.create(member=member, phone_number=number, region="1-US", **flags)

    @staticmethod
    def context(**overrides):
        return Context(**{"mode": UPDATE_EXISTING, "is_master": False, **overrides})

    def analyse(self, rows, headers=HEADERS, **context):
        parsed = read(headers, rows).rows
        return analyse_rows(parsed, load_snapshot(parsed), self.context(**context))

    def analyse_one(self, cells_row, headers=HEADERS, **context):
        return self.analyse([cells_row], headers, **context)[0]

    def apply(self, rows, selections=None, headers=HEADERS, actor=None, **context):
        """Analyse and apply ``rows`` with ``selections`` (``{row number: (choice, ticks)}``), like a confirmed review."""
        parsed = read(headers, rows).rows
        ctx = self.context(**context)
        first = analyse_rows(parsed, load_snapshot(parsed), ctx)
        members = lock_members(m for a in first for m in (a.slice.get("members") or {}))
        snapshot = load_snapshot(parsed)
        analyses = analyse_rows(parsed, snapshot, ctx)
        return run_import(
            analyses,
            selections or {},
            snapshot,
            password_hash="!",
            members=members,
            actor_id=actor.pk if actor else None,
            label="test",
        )

    def stage(self, rows, user, headers=HEADERS, password="", **context):
        """A batch in review for ``rows``, uploaded by ``user``."""
        return create_batch(
            read(headers, rows),
            user=user,
            mode=context.get("mode", UPDATE_EXISTING),
            password=password,
            ctx=self.context(**context),
        )
