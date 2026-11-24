"""Admin accounts: the lockout rules every path that removes an Admin must apply."""

from .lockout import DEACTIVATE, DELETE, DEMOTE, admin_removal_refusal

__all__ = ["DEACTIVATE", "DELETE", "DEMOTE", "admin_removal_refusal"]
