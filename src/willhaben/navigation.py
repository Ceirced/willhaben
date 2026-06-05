from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .client import WillhabenClient
from .constants import MARKETPLACE_PATH

_TRAILING_ID = re.compile(r"-(\d+)$")

_NAVIGATOR_TYPES = {
    "TEXT_SEARCH": "TEXT",
    "STANDARD": "SELECT",
    "RANGE": "RANGE",
    "HIERARCHICAL": "HIERARCHICAL",
}


class FilterType(StrEnum):
    RANGE = "RANGE"
    SELECT = "SELECT"
    HIERARCHICAL = "HIERARCHICAL"
    TEXT = "TEXT"


class SelectionMode(StrEnum):
    SINGLE = "SINGLE"
    MULTI = "MULTI"


@dataclass(frozen=True, slots=True)
class FilterValue:
    label: str
    value: str          # the id to send in the URL param, e.g. "2537"
    hits: int | None


@dataclass(frozen=True, slots=True)
class Filter:
    id: str                       # navigator id, e.g. "Speicherkapazität"
    label: str
    params: tuple[str, ...]       # ("treeAttributes",) or ("PRICE_FROM", "PRICE_TO")
    type: FilterType
    selection: SelectionMode
    values: tuple[FilterValue, ...]


@dataclass(frozen=True, slots=True)
class Category:
    id: int             # ATTRIBUTE_TREE id, e.g. 5015997
    label: str
    hits: int | None


@dataclass(frozen=True, slots=True)
class Crumb:
    label: str
    node_id: int | None


def _iter_values(nav: dict[str, Any]) -> list[dict[str, Any]]:
    values = list(nav.get("possibleValues") or [])
    for grouped in nav.get("groupedPossibleValues") or []:
        values.extend(grouped.get("possibleValues") or [])
    return values


def _url_value(value: dict[str, Any], param: str | None = None) -> str | None:
    for rep in value.get("urlParamRepresentationForValue") or []:
        if param is None or rep.get("urlParameterName") == param:
            raw = rep.get("value")
            if raw is not None:
                return str(raw)
    return None


def _parse_categories(nav: dict[str, Any]) -> list[Category]:
    out: list[Category] = []
    for value in _iter_values(nav):
        raw_id = _url_value(value, "ATTRIBUTE_TREE")
        if raw_id is None:
            continue
        out.append(
            Category(id=int(raw_id), label=value.get("label", ""), hits=value.get("hits"))
        )
    return out


def _parse_filter(nav: dict[str, Any]) -> Filter:
    url_info = nav.get("urlConstructionInformation") or {}
    params = tuple(
        p["urlParameterName"]
        for p in (url_info.get("urlParams") or [])
        if "urlParameterName" in p
    )
    values: list[FilterValue] = []
    for value in _iter_values(nav):
        raw = _url_value(value)
        if raw is None:
            continue
        values.append(
            FilterValue(label=value.get("label", ""), value=raw, hits=value.get("hits"))
        )
    return Filter(
        id=nav.get("id", ""),
        label=nav.get("label", ""),
        params=params,
        type=FilterType(_NAVIGATOR_TYPES.get(nav.get("navigatorType", ""), "SELECT")),
        selection=(
            SelectionMode.MULTI
            if nav.get("navigatorSelectionType") == "MULTI_SELECT"
            else SelectionMode.SINGLE
        ),
        values=tuple(values),
    )


def _parse_breadcrumbs(raw: list[dict[str, Any]]) -> list[Crumb]:
    crumbs: list[Crumb] = []
    for item in raw:
        segment = (item.get("seoUrl", "") or "").rstrip("/").rsplit("/", 1)[-1]
        match = _TRAILING_ID.search(segment)
        crumbs.append(
            Crumb(
                label=item.get("displayName", ""),
                node_id=int(match.group(1)) if match else None,
            )
        )
    return crumbs


@dataclass(frozen=True, slots=True)
class NodeView:
    node_id: int | None
    rows_found: int
    breadcrumbs: tuple[Crumb, ...]
    categories: tuple[Category, ...]   # children; () at a leaf
    filters: tuple[Filter, ...]        # every non-category navigator

    @classmethod
    def from_api(cls, raw: dict[str, Any], *, node_id: int | None) -> NodeView:
        categories: list[Category] = []
        filters: list[Filter] = []
        for group in raw.get("navigatorGroups", []):
            for nav in group.get("navigatorList", []):
                if nav.get("id") == "category":
                    categories.extend(_parse_categories(nav))
                else:
                    filters.append(_parse_filter(nav))
        return cls(
            node_id=node_id,
            rows_found=raw.get("rowsFound", 0),
            breadcrumbs=tuple(_parse_breadcrumbs(raw.get("breadcrumbs", []))),
            categories=tuple(categories),
            filters=tuple(filters),
        )


def navigate(
    node: int | None = None, *, client: WillhabenClient | None = None
) -> NodeView:
    """Fetch a marketplace catalog node and return its child categories and the
    filters valid there.

    `node` is an `ATTRIBUTE_TREE` category id (any depth — e.g. 2724 for Apple,
    5015997 for the iPhone 17 Pro leaf), or `None` for the marketplace root.
    Performs one live request. `categories` is empty at a leaf; `filters` holds
    every non-category navigator (price, condition, storage, …) with its URL
    parameter name, type, selection mode, and possible values.
    """
    client = client or WillhabenClient()
    params: dict[str, str | int | list[int]] = {"rows": 1}
    if node is not None:
        params["ATTRIBUTE_TREE"] = node
    return NodeView.from_api(client.search(MARKETPLACE_PATH, params), node_id=node)
