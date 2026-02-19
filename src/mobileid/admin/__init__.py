"""
MobileID admin configuration.

Includes a barcode scanning interface for the Transaction model that
supports both camera-based scanning (html5-qrcode) and manual input.
"""

from .barcode import BarcodeAdmin
from .mobileid import MobileIDAdmin
from .transaction import TransactionAdmin

__all__ = [
    "BarcodeAdmin",
    "MobileIDAdmin",
    "TransactionAdmin",
]
