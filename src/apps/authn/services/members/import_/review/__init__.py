"""The member import review: Upload → Review → Confirm → Result.

An upload is read (``..reader``), analysed against the stored members (``analysis``) and staged as a batch
(``batches``); nothing touches member data until the admin confirms. The apply (``apply``) re-reads every record the
review read, refuses rows whose records changed, and writes every row in one transaction. ``purge`` enforces the
retention of staged imports.
"""

from .analysis import Context, analyse_rows
from .apply import ApplyResult, apply_batch, lock_members, run_import
from .batches import create_batch, discard_batch, save_choices, stored_analysis
from .lookup import load_snapshot
from .purge import purge_member_imports

__all__ = [
    "ApplyResult",
    "Context",
    "analyse_rows",
    "apply_batch",
    "create_batch",
    "discard_batch",
    "load_snapshot",
    "lock_members",
    "purge_member_imports",
    "run_import",
    "save_choices",
    "stored_analysis",
]
