"""Type-to-confirm for the admin: an add / change / delete (``ConfirmOnSaveMixin``) or a bulk action
(``ConfirmActionMixin``) is held until the admin types the confirmation word, after seeing what will change."""

from .on_action import ConfirmActionMixin
from .on_save import ConfirmOnSaveMixin

__all__ = ["ConfirmActionMixin", "ConfirmOnSaveMixin"]
