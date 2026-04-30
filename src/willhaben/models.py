from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def _attrs_to_dict(raw_attrs: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {a["name"]: a["values"] for a in raw_attrs}


def _first(values: list[str] | None) -> str | None:
    return values[0] if values else None


def _parse_coords(raw: str | None) -> tuple[float, float] | None:
    if not raw:
        return None
    try:
        lat, lon = raw.split(",", 1)
        return float(lat), float(lon)
    except ValueError:
        return None


def _parse_published(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
    except (TypeError, ValueError):
        return None


def _parse_price(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _state_counts_from_raw(raw: dict[str, Any]) -> dict[int, int]:
    nav = next(
        (
            n
            for g in raw.get("navigatorGroups", [])
            for n in g.get("navigatorList", [])
            if n.get("id") == "state"
        ),
        None,
    )
    if nav is None:
        return {}
    values: list[dict[str, Any]] = list(nav.get("possibleValues") or [])
    for grouped in nav.get("groupedPossibleValues") or []:
        values.extend(grouped.get("possibleValues") or [])
    counts: dict[int, int] = {}
    for v in values:
        hits = v.get("hits")
        if hits is None:
            continue
        for p in v.get("urlParamRepresentationForValue") or []:
            if p.get("urlParameterName") == "areaId":
                try:
                    counts[int(p["value"])] = hits
                except (KeyError, ValueError, TypeError):
                    pass
                break
    return counts


@dataclass(frozen=True, slots=True)
class Ad:
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
    body: str | None
    main_image_url: str | None
    is_private: bool
    raw_attributes: dict[str, list[str]] = field(repr=False)

    def __repr__(self):
        return f"Ad(id={self.id}, title={self.title!r}, price={self.price}, url={self.url})"

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Ad:
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
            price=_parse_price(_first(attrs.get("PRICE/AMOUNT"))),
            price_display=_first(attrs.get("PRICE_FOR_DISPLAY")),
            location=_first(attrs.get("LOCATION")),
            postcode=_first(attrs.get("POSTCODE")),
            district=_first(attrs.get("DISTRICT")),
            state=_first(attrs.get("STATE")),
            coordinates=_parse_coords(_first(attrs.get("COORDINATES"))),
            published_at=_parse_published(_first(attrs.get("PUBLISHED"))),
            body=_first(attrs.get("BODY_DYN")),
            main_image_url=main_image,
            is_private=_first(attrs.get("ISPRIVATE")) == "1",
            raw_attributes=attrs,
        )


@dataclass(frozen=True, slots=True)
class SearchResult:
    rows_found: int
    rows_returned: int
    page: int
    ads: list[Ad]
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def counts_by_state(self) -> dict[int, int]:
        """Map Bundesland areaId → ad count. Keys match `AREAS`."""
        return _state_counts_from_raw(self.raw)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> SearchResult:
        ad_list = raw.get("advertSummaryList", {}).get("advertSummary", [])
        return cls(
            rows_found=raw.get("rowsFound", 0),
            rows_returned=raw.get("rowsReturned", 0),
            page=raw.get("pageRequested", 1),
            ads=[Ad.from_api(a) for a in ad_list],
            raw=raw,
        )
