"""Client-side auto-pagination for ``records list``.

The backend list endpoint (``/admin-api/records/<app>/<model>/``) returns
``{model, count, offset, limit, results}`` and caps ``limit`` at 50 (MAX_ROWS).
To mirror AWS-CLI behavior, :func:`paginate` walks the offset/limit window for
the caller, accumulating ``results`` across pages until the server's ``count``
is reached (or ``--max-items`` truncates the stream), then returns a single
``{model, count, results}`` dict for the formatter to render.
"""

# Server-side cap on rows per page (MAX_ROWS in apps.cli_admin); requesting more
# is silently clamped, so we never ask for more than this.
MAX_PAGE_SIZE = 50


def _page_params(base_params, *, limit, offset):
    """Return ``base_params`` with limit/offset appended (base_params untouched)."""
    return list(base_params) + [("limit", str(limit)), ("offset", str(offset))]


def paginate(client, path, base_params, *, no_paginate, max_items, page_size) -> dict:
    """Fetch one or all pages of a record list.

    With ``no_paginate`` true, issue a single GET and return the raw response
    dict (today's behavior). Otherwise loop over pages of ``page_size`` (capped
    at :data:`MAX_PAGE_SIZE`), accumulating ``results`` until the server's
    ``count`` is reached, ``max_items`` is hit, or a page comes back empty.
    """
    if no_paginate:
        return client.get(path, params=list(base_params))

    limit = min(page_size or MAX_PAGE_SIZE, MAX_PAGE_SIZE)
    offset = 0
    accumulated: list = []
    model = None
    count = 0
    while True:
        page = client.get(path, params=_page_params(base_params, limit=limit, offset=offset))
        model = page.get("model", model)
        count = page.get("count", count)
        rows = page.get("results") or []
        if not rows:
            break
        accumulated.extend(rows)
        offset += len(rows)
        if max_items is not None and len(accumulated) >= max_items:
            accumulated = accumulated[:max_items]
            break
        if len(accumulated) >= count:
            break
    return {"model": model, "count": count, "results": accumulated}
