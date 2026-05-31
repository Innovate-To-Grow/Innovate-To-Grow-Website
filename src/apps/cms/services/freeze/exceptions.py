"""Exceptions raised by the page-freeze service."""

from .ssrf import BlockedURLError

__all__ = ["BlockedURLError", "FreezeError", "FreezeFetchError"]


class FreezeError(Exception):
    """A page could not be frozen (parse, selector, or size error)."""


class FreezeFetchError(FreezeError):
    """The source page could not be fetched (transport or HTTP error)."""
