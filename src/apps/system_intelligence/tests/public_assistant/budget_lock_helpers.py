"""Reading the order in which budget rows were locked."""

from django.db import connection


def _budget_row_lock_order(queries, keys):
    """Order in which budget rows were first SELECTed (locked, on PostgreSQL)."""
    order = []
    for query in queries:
        sql = query["sql"]
        if not sql.lstrip().upper().startswith("SELECT") or "publicassistanttokenbudget" not in sql.lower():
            continue
        for key in keys:
            if key in sql and key not in order:
                if connection.features.has_select_for_update:
                    assert "FOR UPDATE" in sql.upper(), sql
                order.append(key)
    return order
