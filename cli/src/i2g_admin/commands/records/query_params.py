"""Shared query-parameter builders for the ``records`` commands.

``records list``, ``records count``, and ``records wait`` all turn a repeatable
``--filter key=value`` option into ``[("filter", item), ...]`` query params. This
module is the single place that mapping lives, so the three commands stay in sync.
"""


def filter_params(filter_) -> list[tuple[str, str]]:
    """Return ``[("filter", item), ...]`` for each ``--filter`` value (None -> [])."""
    return [("filter", item) for item in filter_ or []]


def list_query_params(filter_, order, field) -> list[tuple[str, str]]:
    """Build the ``records list`` query params: filters, then orders, then fields.

    Each option is repeatable; a None option contributes nothing. ``limit`` and
    ``offset`` are intentionally left to the caller since they branch the
    pagination behavior.
    """
    params = filter_params(filter_)
    params.extend(("order", item) for item in order or [])
    params.extend(("field", item) for item in field or [])
    return params
