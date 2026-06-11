from __future__ import annotations

from collections.abc import Iterator

from .client import QueryValue, WillhabenClient
from .constants import MAX_ROWS_PER_PAGE, SortOrder
from .models import Ad, SearchResult
from .navigation import Order
from .verticals import _target


def _execute(
    order: Order,
    *,
    rows: int,
    page: int,
    sort: SortOrder | int | None,
    client: WillhabenClient,
) -> SearchResult:
    path, node_params = _target(order.vertical, order.node)
    params: dict[str, QueryValue] = {**node_params}
    params.update(order.params)
    params["rows"] = rows  # pagination control is pinned; never overridden by order.params
    params["page"] = page
    # the sort kwarg overrides any sort already in order.params; sort=None leaves it untouched
    if sort is not None:
        params["sort"] = int(sort)
    return SearchResult.from_api(client.search(path, params), vertical=order.vertical)


def search(
    order: Order,
    *,
    rows: int = 30,
    page: int = 1,
    sort: SortOrder | int | None = None,
    client: WillhabenClient | None = None,
) -> SearchResult:
    """Run a single search for an Order. `rows` is server-capped at 200."""
    client = client or WillhabenClient()
    return _execute(order, rows=rows, page=page, sort=sort, client=client)


def count(order: Order, *, client: WillhabenClient | None = None) -> int:
    """Return only the total result count for an Order via a `rows=1` request."""
    client = client or WillhabenClient()
    return _execute(order, rows=1, page=1, sort=None, client=client).rows_found


def iter_ads(
    order: Order,
    *,
    max_results: int | None = None,
    sort: SortOrder | int | None = None,
    client: WillhabenClient | None = None,
) -> Iterator[Ad]:
    """Yield ads for an Order across all pages, stopping at `max_results`."""
    client = client or WillhabenClient()
    yielded = 0
    page = 1
    while True:
        result = _execute(order, rows=MAX_ROWS_PER_PAGE, page=page, sort=sort, client=client)
        if not result.ads:
            return
        for ad in result.ads:
            yield ad
            yielded += 1
            if max_results is not None and yielded >= max_results:
                return
        if yielded >= result.rows_found:
            return
        page += 1
