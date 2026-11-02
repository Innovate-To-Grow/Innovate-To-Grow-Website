"""Archive ordering: newest semester first, then class, then team in numeric order."""

from django.db.models import F, Value
from django.db.models.functions import LPad, Replace

# team_number is text, so plain ordering puts "10" before "2". Padding it with zeros sorts it as a number, and
# dropping the class code first reads 2021's prefixed Team# ("CAP02") as 2 as well. 20 is the column's length,
# so padding never truncates.
_TEAM_NUMBER_SORT_KEY = LPad(Replace("team_number", F("class_code"), Value("")), 20, Value("0"))


def team_ordering() -> tuple:
    """Class, then team number as a number (the raw text breaks ties)."""
    return ("class_code", _TEAM_NUMBER_SORT_KEY, "team_number")


def archive_ordering() -> tuple:
    """Newest semester first, then :func:`team_ordering`."""
    return ("-semester__year", "-semester__season", *team_ordering())
