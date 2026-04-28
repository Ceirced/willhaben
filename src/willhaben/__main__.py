from __future__ import annotations

from .constants import AREAS, SortOrder
from .search import count, search


def main() -> None:
    total = count(keyword="fahrrad")
    print(f"Fahrrad (all): {total:,} results")  # noqa: T201

    result = search(
        keyword="fahrrad",
        price_from=50,
        price_to=200,
        area_id=AREAS["wien"],
        sort=SortOrder.NEWEST,
        rows=5,
    )
    print(  # noqa: T201
        f"\nFahrrad €50-200 in Wien: {result.rows_found:,} total, "
        f"showing {len(result.ads)}"
    )
    for ad in result.ads:
        price = ad.price_display or "—"
        loc = ad.location or "?"
        print(f"  [{ad.id}] {ad.title}")  # noqa: T201
        print(f"    {price} · {loc} · {ad.url}")  # noqa: T201


if __name__ == "__main__":
    main()
