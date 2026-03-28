"""
Models for the mail app — Gmail and SES sender configuration plus audit logs.
"""

from .model_accounts import GoogleAccount, SESAccount
from .model_logs import EmailLog, SESEmailLog

__all__ = [
    "GoogleAccount",
    "EmailLog",
    "SESAccount",
    "SESEmailLog",
]
