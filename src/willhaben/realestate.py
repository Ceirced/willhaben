from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from typing import Any

from .client import WillhabenClient
from .constants import MAX_ROWS_PER_PAGE, SortOrder
from .models import (
    _attrs_to_dict,
    _first,
    _parse_coords,
    _parse_price,
    _parse_published,
)


class RealEstateCategory(IntEnum):
    ALL = 90
    NEW_CONSTRUCTION = 42
    HOUSE_BUY = 102
    HOUSE_RENT = 132
    APARTMENT_BUY = 101
    APARTMENT_RENT = 131
    LAND = 14
    COMMERCIAL_BUY = 15
    COMMERCIAL_RENT = 16
    HOLIDAY_BUY = 12
    HOLIDAY_RENT = 32
    OTHER = 35


def _parse_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class RealEstateAd:
    id: str
    title: str
    url: str
    seo_url: str | None
    price: Decimal | None
    price_display: str | None
    location: str | None
    postcode: str | None
    district: str | None
    state: str | None
    coordinates: tuple[float, float] | None
    published_at: datetime | None
    main_image_url: str | None

    rooms: int | None
    area_m2: Decimal | None
    property_type: str | None
    property_type_id: int | None
    free_area_type: str | None

    is_private: bool
    raw_attributes: dict[str, list[str]] = field(repr=False)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> RealEstateAd:
        attrs = _attrs_to_dict(raw.get("attributes", {}).get("attribute", []))
        ad_id = str(raw["id"])

        seo_path = _first(attrs.get("SEO_URL"))
        seo_full = f"https://www.willhaben.at/iad/{seo_path}" if seo_path else None
        share_link = next(
            (
                c["uri"]
                for c in raw.get("contextLinkList", {}).get("contextLink", [])
                if c.get("id") == "iadShareLink"
            ),
            None,
        )
        url = (
            share_link
            or seo_full
            or f"https://www.willhaben.at/iad/object?adId={ad_id}"
        )

        images = raw.get("advertImageList", {}).get("advertImage", [])
        main_image = images[0]["mainImageUrl"] if images else None

        return cls(
            id=ad_id,
            title=raw.get("description", ""),
            url=url,
            seo_url=seo_full,
            price=_parse_price(_first(attrs.get("PRICE"))),
            price_display=_first(attrs.get("PRICE_FOR_DISPLAY")),
            location=_first(attrs.get("LOCATION")),
            postcode=_first(attrs.get("POSTCODE")),
            district=_first(attrs.get("DISTRICT")),
            state=_first(attrs.get("STATE")),
            coordinates=_parse_coords(_first(attrs.get("COORDINATES"))),
            published_at=_parse_published(_first(attrs.get("PUBLISHED"))),
            main_image_url=main_image,
            rooms=_parse_int(_first(attrs.get("NUMBER_OF_ROOMS"))),
            # _parse_price returns Decimal | None — reused for the m² value.
            area_m2=_parse_price(_first(attrs.get("ESTATE_SIZE/LIVING_AREA"))),
            property_type=_first(attrs.get("PROPERTY_TYPE")),
            property_type_id=_parse_int(_first(attrs.get("PROPERTY_TYPE_ID"))),
            free_area_type=_first(attrs.get("FREE_AREA_TYPE_NAME")),
            is_private=_first(attrs.get("ISPRIVATE")) == "1",
            raw_attributes=attrs,
        )


@dataclass(frozen=True, slots=True)
class RealEstateSearchResult:
    rows_found: int
    rows_returned: int
    page: int
    ads: list[RealEstateAd]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> RealEstateSearchResult:
        ad_list = raw.get("advertSummaryList", {}).get("advertSummary", [])
        return cls(
            rows_found=raw.get("rowsFound", 0),
            rows_returned=raw.get("rowsReturned", 0),
            page=raw.get("pageRequested", 1),
            ads=[RealEstateAd.from_api(a) for a in ad_list],
        )


def _build_realestate_params(
    *,
    keyword: str | None,
    price_from: int | None,
    price_to: int | None,
    area_m2_from: int | None,
    area_m2_to: int | None,
    rooms: str | None,
    property_type: int | None,
    area_id: int | None,
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
    if area_m2_from is not None:
        params["ESTATE_SIZE/LIVING_AREA_FROM"] = area_m2_from
    if area_m2_to is not None:
        params["ESTATE_SIZE/LIVING_AREA_TO"] = area_m2_to
    if rooms is not None:
        params["NO_OF_ROOMS_BUCKET"] = rooms
    if property_type is not None:
        params["PROPERTY_TYPE"] = property_type
    if area_id is not None:
        params["areaId"] = area_id
    if is_private is True:
        params["ISPRIVATE"] = 1
    if sort is not None:
        params["sort"] = int(sort)
    if extra:
        params.update(extra)
    return params


def search_realestate(
    *,
    category: RealEstateCategory,
    keyword: str | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
    area_m2_from: int | None = None,
    area_m2_to: int | None = None,
    rooms: str | None = None,
    property_type: int | None = None,
    area_id: int | None = None,
    is_private: bool | None = None,
    sort: SortOrder | int | None = None,
    rows: int = 30,
    page: int = 1,
    client: WillhabenClient | None = None,
    extra_params: dict[str, str | int] | None = None,
) -> RealEstateSearchResult:
    """Run a single real-estate search query.

    `rooms` is a willhaben "bucket" string like "2X2" (exactly 2 rooms) or
    "2X4" (2-to-4 rooms). `area_id` uses `AREAS`. `rows` is server-capped
    at 200.
    """
    client = client or WillhabenClient()
    params = _build_realestate_params(
        keyword=keyword,
        price_from=price_from,
        price_to=price_to,
        area_m2_from=area_m2_from,
        area_m2_to=area_m2_to,
        rooms=rooms,
        property_type=property_type,
        area_id=area_id,
        is_private=is_private,
        sort=sort,
        rows=rows,
        page=page,
        extra=extra_params,
    )
    path = f"atz/2/{category.value}"
    return RealEstateSearchResult.from_api(client.search(path, params))


def count_realestate(
    *,
    category: RealEstateCategory,
    keyword: str | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
    area_m2_from: int | None = None,
    area_m2_to: int | None = None,
    rooms: str | None = None,
    property_type: int | None = None,
    area_id: int | None = None,
    is_private: bool | None = None,
    client: WillhabenClient | None = None,
    extra_params: dict[str, str | int] | None = None,
) -> int:
    """Return only the total result count via a minimal `rows=1` request."""
    return search_realestate(
        category=category,
        keyword=keyword,
        price_from=price_from,
        price_to=price_to,
        area_m2_from=area_m2_from,
        area_m2_to=area_m2_to,
        rooms=rooms,
        property_type=property_type,
        area_id=area_id,
        is_private=is_private,
        rows=1,
        client=client,
        extra_params=extra_params,
    ).rows_found


def iter_realestate_ads(
    *,
    category: RealEstateCategory,
    keyword: str | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
    area_m2_from: int | None = None,
    area_m2_to: int | None = None,
    rooms: str | None = None,
    property_type: int | None = None,
    area_id: int | None = None,
    is_private: bool | None = None,
    sort: SortOrder | int | None = None,
    max_results: int | None = None,
    client: WillhabenClient | None = None,
    extra_params: dict[str, str | int] | None = None,
) -> Iterator[RealEstateAd]:
    """Yield real-estate ads across all pages, stopping at `max_results` if given."""
    client = client or WillhabenClient()
    yielded = 0
    page = 1
    while True:
        result = search_realestate(
            category=category,
            keyword=keyword,
            price_from=price_from,
            price_to=price_to,
            area_m2_from=area_m2_from,
            area_m2_to=area_m2_to,
            rooms=rooms,
            property_type=property_type,
            area_id=area_id,
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
