from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from typing import Any, Final

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


# Real estate uses different areaId values than the marketplace `AREAS` dict.
# Wien is the only value that matches.
REAL_ESTATE_AREAS: Final[dict[str, int]] = {
    "burgenland": 1,
    "kärnten": 2,
    "niederösterreich": 3,
    "oberösterreich": 4,
    "salzburg": 5,
    "steiermark": 6,
    "tirol": 7,
    "vorarlberg": 8,
    "wien": 900,
    "andere länder": 22000,
}


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
