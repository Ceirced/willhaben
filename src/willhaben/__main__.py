from __future__ import annotations

from . import AREAS, MARKETPLACE, SortOrder, count, navigate, search


def main() -> None:
    view = navigate(vertical=MARKETPLACE)
    order = view.order(
        select={"keyword": "fahrrad", "price": (50, 200)},
        extra={"areaId": AREAS["wien"].id},
    )
    total = count(order)
    print(f"Fahrrad €50-200 in Wien: {total:,} results")  # noqa: T201

    result = search(order, sort=SortOrder.NEWEST, rows=5)
    print(f"\nShowing {len(result.ads)} of {result.rows_found:,}")  # noqa: T201
    for ad in result.ads:
        price = ad.price_display or "—"
        loc = ad.location or "?"
        print(f"  [{ad.id}] {ad.title}")  # noqa: T201
        print(f"    {price} · {loc} · {ad.url}")  # noqa: T201


if __name__ == "__main__":
    main()
