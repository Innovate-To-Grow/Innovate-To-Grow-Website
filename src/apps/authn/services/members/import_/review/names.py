"""Whether a sheet row's name and a member's name can be the same person.

Both names are normalised: Unicode NFKD without accents, case-folded, ``. , '`` dropped, hyphens read as spaces,
spaces collapsed. Last names agree when they are equal (ignoring spaces) or when one is a whole word of the other
(double-barrelled names). First names agree when one is a prefix of the other, ignoring spaces: "Chris" /
"Christopher", "C." / "Christopher", "Mary-Jane" / "Mary Jane". Middle names are not compared, and a blank name on
either side is never a mismatch. Anything else needs the admin's decision (conflict C6).
"""

from __future__ import annotations

import re
import unicodedata

_DROPPED = re.compile(r"[.,'’]")
_SPACES = re.compile(r"[\s\-]+")


def normalize_name(name: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", name or "")
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _SPACES.sub(" ", _DROPPED.sub("", plain.casefold())).strip()


def _squash(name: str) -> str:
    return name.replace(" ", "")


def _last_names_agree(sheet: str, stored: str) -> bool:
    return _squash(sheet) == _squash(stored) or sheet in stored.split() or stored in sheet.split()


def _first_names_agree(sheet: str, stored: str) -> bool:
    return _squash(sheet).startswith(_squash(stored)) or _squash(stored).startswith(_squash(sheet))


def names_agree(sheet_first: str, sheet_last: str, stored_first: str, stored_last: str) -> bool:
    """Whether the sheet's first and last name can be the stored member's (blank cells are not compared)."""
    pairs = (
        (normalize_name(sheet_first), normalize_name(stored_first), _first_names_agree),
        (normalize_name(sheet_last), normalize_name(stored_last), _last_names_agree),
    )
    return all(not sheet or not stored or agree(sheet, stored) for sheet, stored, agree in pairs)
