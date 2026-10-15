"""Private, read-only gateway for the retired I2G Flask application."""

from .urls import get_legacy_view_urls

__all__ = ["get_legacy_view_urls"]
