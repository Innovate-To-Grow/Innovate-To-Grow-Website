"""Edge-case tests for paginate(): null/missing count, negative max-items, shapes."""

import pytest
from i2g_admin.commands.records.pagination import paginate
from i2g_admin.core.errors import CliError
from test_pagination import PATH, PageClient


# ---- null / missing count must not break or stop early --------------------
def test_null_count_does_not_raise():
    # count=None previously hit `len(accumulated) >= None` -> TypeError.
    pages = [
        {"model": "m", "count": None, "results": [{"i": 0}]},
        {"model": "m", "count": None, "results": []},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=1)
    assert [r["i"] for r in result["results"]] == [0]
    assert result["count"] == 0
    # Two GETs: one row page, then an empty page that terminates.
    assert len(client.calls) == 2


def test_missing_count_key_walks_all_pages():
    # Without a count key, the loop must rely on the empty-page terminator and
    # not stop after the first page (the old `count` default of 0 did: 1 >= 0).
    pages = [
        {"model": "m", "results": [{"i": 0}, {"i": 1}]},
        {"model": "m", "results": [{"i": 2}]},
        {"model": "m", "results": []},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=2)
    assert [r["i"] for r in result["results"]] == [0, 1, 2]
    assert len(client.calls) == 3


# ---- negative --max-items is rejected --------------------------------------
def test_negative_max_items_raises():
    client = PageClient([{"model": "m", "count": 3, "results": [{"i": 0}, {"i": 1}, {"i": 2}]}])
    with pytest.raises(CliError):
        paginate(client, PATH, [], no_paginate=False, max_items=-1, page_size=50)


def test_negative_max_items_raises_even_with_no_paginate():
    client = PageClient([{"model": "m", "count": 3, "results": [{"i": 0}]}])
    with pytest.raises(CliError):
        paginate(client, PATH, [], no_paginate=True, max_items=-2, page_size=None)


# ---- --no-paginate honors --max-items --------------------------------------
def test_no_paginate_applies_max_items():
    client = PageClient([{"model": "m", "count": 99, "results": [{"i": n} for n in range(50)]}])
    result = paginate(client, PATH, [], no_paginate=True, max_items=5, page_size=None)
    assert [r["i"] for r in result["results"]] == [0, 1, 2, 3, 4]
    # count stays the server-side total; only the rows are truncated.
    assert result["count"] == 99
    assert len(client.calls) == 1


def test_no_paginate_max_items_zero_yields_no_rows():
    client = PageClient([{"model": "m", "count": 3, "results": [{"i": 0}, {"i": 1}]}])
    result = paginate(client, PATH, [], no_paginate=True, max_items=0, page_size=None)
    assert result["results"] == []
    assert result["count"] == 3


# ---- all three list shapes agree -------------------------------------------
def test_accumulated_shape_includes_offset_and_limit():
    pages = [
        {"model": "m", "count": 3, "results": [{"i": 0}, {"i": 1}]},
        {"model": "m", "count": 3, "results": [{"i": 2}]},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=2)
    assert set(result) == {"model", "count", "offset", "limit", "results"}
    assert result["offset"] == 0
    assert result["limit"] == 2
