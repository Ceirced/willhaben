from __future__ import annotations

from collections.abc import Iterator

from .client import WillhabenClient
from .constants import MAX_ROWS_PER_PAGE, SortOrder
from .models import Ad, SearchResult


def _build_params(
    *,
    keyword: str | None,
    price_from: int | None,
    price_to: int | None,
    area_id: int | None,
    category_id: int | None,
    is_private: bool | None,
    sort: SortOrder | int | None,
    rows: int,
    page: int,
    extra: dict[str, str | int] | None,
) -> dict[str, str | int]:
    params: dict[str, str | int] = {"rows": rows, "page": page}
    if keyword:
        params["keyword"] = keyword
    if price_from is not None:
        params["PRICE_FROM"] = price_from
    if price_to is not None:
        params["PRICE_TO"] = price_to
    if area_id is not None:
        params["areaId"] = area_id
    if category_id is not None:
        params["categoryId"] = category_id
    if is_private is True:
        params["ISPRIVATE"] = 1
    if sort is not None:
        params["sort"] = int(sort)
    if extra:
        params.update(extra)
    return params


def search(
    *,
    keyword: str | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
    area_id: int | None = None,
    category_id: int | None = None,
    is_private: bool | None = None,
    sort: SortOrder | int | None = None,
    rows: int = 30,
    page: int = 1,
    client: WillhabenClient | None = None,
    extra_params: dict[str, str | int] | None = None,
) -> SearchResult:
    """Run a single search query. `rows` is server-capped at 200."""
    client = client or WillhabenClient()
    params = _build_params(
        keyword=keyword,
        price_from=price_from,
        price_to=price_to,
        area_id=area_id,
        category_id=category_id,
        is_private=is_private,
        sort=sort,
        rows=rows,
        page=page,
        extra=extra_params,
    )
    return SearchResult.from_api(client.search(params))


def count(
    *,
    keyword: str | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
    area_id: int | None = None,
    category_id: int | None = None,
    is_private: bool | None = None,
    client: WillhabenClient | None = None,
    extra_params: dict[str, str | int] | None = None,
) -> int:
    """Return only the total result count via a minimal `rows=1` request."""
    return search(
        keyword=keyword,
        price_from=price_from,
        price_to=price_to,
        area_id=area_id,
        category_id=category_id,
        is_private=is_private,
        rows=1,
        client=client,
        extra_params=extra_params,
    ).rows_found


def iter_ads(
    *,
    keyword: str | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
    area_id: int | None = None,
    category_id: int | None = None,
    is_private: bool | None = None,
    sort: SortOrder | int | None = None,
    max_results: int | None = None,
    client: WillhabenClient | None = None,
    extra_params: dict[str, str | int] | None = None,
) -> Iterator[Ad]:
    """Yield ads across all pages, stopping at `max_results` if given."""
    client = client or WillhabenClient()
    yielded = 0
    page = 1
    while True:
        result = search(
            keyword=keyword,
            price_from=price_from,
            price_to=price_to,
            area_id=area_id,
            category_id=category_id,
            is_private=is_private,
            sort=sort,
            rows=MAX_ROWS_PER_PAGE,
            page=page,
            client=client,
            extra_params=extra_params,
        )
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
