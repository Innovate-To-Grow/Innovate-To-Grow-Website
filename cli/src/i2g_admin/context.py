"""Shared per-invocation context carrying the global options.

The Typer root callback (:func:`i2g_admin.app.main`) populates a :class:`Context`
into ``typer.Context.obj`` once; command functions read it via
:func:`get_context`. Every global option a wave-2 unit needs is declared here
and on the callback up front, so no later unit has to edit the callback
signature — they only read the field they care about.
"""

from dataclasses import dataclass

from . import auth
from .client import ApiClient


@dataclass
class Context:
    profile: str | None = None
    output: str = "table"
    query: str | None = None
    # U4 pagination
    no_paginate: bool = False
    max_items: int | None = None
    page_size: int | None = None
    # U5 HTTP robustness
    max_attempts: int = 1
    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    debug: bool = False


def get_context(ctx) -> Context:
    """Return the :class:`Context` for this invocation, tolerating a missing callback.

    Commands are sometimes invoked in tests without the root callback running;
    fall back to defaults so those paths still work.
    """
    if getattr(ctx, "obj", None) is None:
        ctx.obj = Context()
    return ctx.obj


def build_client(context: Context) -> ApiClient:
    """Construct an :class:`ApiClient` for the active profile using the global options."""
    base_url, token = auth.ensure_token(profile=context.profile)
    return ApiClient(
        base_url,
        token,
        timeout=(context.connect_timeout, context.read_timeout),
        max_attempts=context.max_attempts,
    )
