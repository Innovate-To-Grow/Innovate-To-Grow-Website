"""Staff actions on a bounced address: which one a staff member may take now (``guards``, ``targets``), what each does
(``handlers``), applying one (``apply``), replacing an address (``replace``), and the records they leave (``audit``)."""

from .apply import APPLY, apply_action
from .effects import ActionRefused, StaleConfirmation
from .handlers import deletion_summary

__all__ = ["ActionRefused", "StaleConfirmation", "apply_action", "deletion_summary"]
