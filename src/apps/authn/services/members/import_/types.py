"""Types used by member import services."""

from dataclasses import dataclass, field


class ImportMessage(str):
    """One line of the import report.

    It is a plain ``str`` wherever it is compared or printed. ``row`` is the spreadsheet row it is about (None for
    the file as a whole), and ``member_id`` names the member it is about, so the admin page can link to that member.
    """

    row: int | None
    member_id: str | None

    def __new__(cls, text: str, row: int | None = None, member=None):
        message = super().__new__(cls, text)
        message.row = row
        message.member_id = str(member.pk) if member is not None else None
        return message


@dataclass
class ImportResult:
    """Result of a member import operation.

    ``errors`` lists the rows that were not imported, and why (plus file-level failures). ``warnings`` lists what an
    imported row asked for but was not applied, or what was kept, and why.
    """

    success: bool
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)

    def skip_row(self, row: int, reason: str, member=None) -> None:
        """Count spreadsheet row ``row`` as skipped and say why."""
        self.skipped_count += 1
        self.errors.append(ImportMessage(f"Row {row}: {reason}", row, member))

    def note_row(self, row: int, note: str, member=None) -> None:
        """Report something an imported row asked for that was not applied, or a contact that was kept."""
        self.warnings.append(ImportMessage(f"Row {row}: {note}", row, member))

    def note_file(self, note: str) -> None:
        """Report something about the file as a whole, such as a column that is ignored; listed before the rows."""
        self.warnings.append(ImportMessage(note))

    def sort_by_row(self) -> None:
        """Order both lists by spreadsheet row; file-level messages (no row) stay first."""
        for messages in (self.errors, self.warnings):
            messages.sort(key=lambda message: getattr(message, "row", None) or 0)
