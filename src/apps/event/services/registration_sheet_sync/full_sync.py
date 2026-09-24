"""Compatibility entry point: reconciliation preserves unmanaged cells."""

from .engine import create_registration_worksheet, inspect_registration_sheet, sync_registrations_to_sheet

__all__ = ["create_registration_worksheet", "inspect_registration_sheet", "sync_registrations_to_sheet"]
