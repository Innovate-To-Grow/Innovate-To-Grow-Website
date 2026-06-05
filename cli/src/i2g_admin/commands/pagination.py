"""Client-side auto-pagination for ``records list``.

The backend list endpoint (``/admin-api/records/<app>/<model>/``) returns
``{model, count, offset, limit, results}`` and caps ``limit`` at 50 (MAX_ROWS).
To mirror AWS-CLI behavior, :func:`paginate` walks the offset/limit window for
the caller, accumulating ``results`` across pages until a page comes back empty
(the primary terminator) or ``--max-items`` truncates the stream, then returns a
single ``{model, count, offset, limit, results}`` dict for the formatter to
render. The shape matches the single-page (``--no-paginate`` / explicit
``--limit``) paths so the three list routes are interchangeable.
"""

from ..errors import CliError

# Server-side cap on rows per page (MAX_ROWS in apps.cli_admin); requesting more
# is silently clamped, so we never ask for more than this.
MAX_PAGE_SIZE = 50


def _page_params(base_params, *, limit, offset):
    """Return ``base_params`` with limit/offset appended (base_params untouched)."""
    return list(base_params) + [("limit", str(limit)), ("offset", str(offset))]


def paginate(client, path, base_params, *, no_paginate, max_items, page_size) -> dict:
    """Fetch one or all pages of a record list.

    With ``no_paginate`` true, issue a single GET and return the raw response
    dict (capped to ``max_items`` rows when given — ``count`` stays the
    server-side total, matching AWS-CLI). Otherwise loop over pages of
    ``page_size`` (capped at :data:`MAX_PAGE_SIZE`), accumulating ``results``
    until a page comes back empty, ``max_items`` is hit, or the server's
    ``count`` is reached.
    """
    if max_items is not None and max_items < 0:
        raise CliError("--max-items must be >= 0.")

    if no_paginate:
        page = client.get(path, params=list(base_params))
        if max_items is not None and isinstance(page, dict):
            page = {**page, "results": (page.get("results") or [])[:max_items]}
        return page

    limit = min(page_size or MAX_PAGE_SIZE, MAX_PAGE_SIZE)
    offset = 0
    accumulated: list = []
    model = None
    count = 0
    while True:
        page = client.get(path, params=_page_params(base_params, limit=limit, offset=offset))
        model = page.get("model", model)
        # count may be null or absent on edge/older servers; treat that as 0 so we
        # rely on the empty-page terminator instead of stopping early (50 >= 0).
        count = page.get("count") or 0
        rows = page.get("results") or []
        if not rows:
            break
        accumulated.extend(rows)
        offset += len(rows)
        if max_items is not None and len(accumulated) >= max_items:
            accumulated = accumulated[:max_items]
            break
        # Only treat count as a terminator when it is a positive total; a 0/None
        # count must not stop us before the first empty page.
        if count > 0 and len(accumulated) >= count:
            break
    return {"model": model, "count": count, "offset": 0, "limit": limit, "results": accumulated}
