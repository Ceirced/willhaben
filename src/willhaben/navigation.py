from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .client import QueryParams, QueryValue, WillhabenClient
from .verticals import MARKETPLACE, Vertical, _target

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
    params: Mapping[str, str]   # this value's URL representation, e.g. {"treeAttributes": "2537"}
    hits: int | None

    @property
    def value(self) -> str | None:
        """The first param value — convenient for single-param discrete filters."""
        return next(iter(self.params.values()), None)


@dataclass(frozen=True, slots=True)
class Filter:
    id: str                       # navigator id, e.g. "Speicherkapazität"
    label: str
    params: tuple[str, ...]       # ("treeAttributes",) or ("PRICE_FROM", "PRICE_TO")
    type: FilterType
    selection: SelectionMode
    values: tuple[FilterValue, ...]
    available: bool


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


def _value_params(value: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rep in value.get("urlParamRepresentationForValue") or []:
        name, raw = rep.get("urlParameterName"), rep.get("value")
        if name is not None and raw is not None:
            out[name] = str(raw)
    return out


def _parse_categories(nav: dict[str, Any]) -> list[Category]:
    out: list[Category] = []
    for value in _iter_values(nav):
        params = _value_params(value)
        if not params:
            continue
        # A category value carries exactly one url param (ATTRIBUTE_TREE for
        # marketplace, searchId for realestate/auto); use its value as the id.
        raw_id = next(iter(params.values()))
        try:
            cat_id = int(raw_id)
        except ValueError:
            continue
        out.append(
            Category(id=cat_id, label=value.get("label", ""), hits=value.get("hits"))
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
        vparams = _value_params(value)
        if not vparams:
            continue
        values.append(
            FilterValue(label=value.get("label", ""), params=vparams, hits=value.get("hits"))
        )
    nav_type = nav.get("navigatorType", "")
    return Filter(
        id=nav.get("id", ""),
        label=nav.get("label", ""),
        params=params,
        type=FilterType(_NAVIGATOR_TYPES.get(nav_type, "SELECT")),
        selection=(
            SelectionMode.MULTI
            if nav.get("navigatorSelectionType") == "MULTI_SELECT"
            else SelectionMode.SINGLE
        ),
        values=tuple(values),
        available=nav_type != "NOT_SELECTABLE",
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
class Order:
    """A persistable, replayable search agent: vertical + node + flat params."""

    vertical: Vertical
    node: int | None
    params: Mapping[str, QueryValue]


@dataclass(frozen=True, slots=True)
class NodeView:
    node_id: int | None
    vertical: Vertical
    rows_found: int
    breadcrumbs: tuple[Crumb, ...]
    categories: tuple[Category, ...]   # children; () at a leaf
    filters: tuple[Filter, ...]        # every non-category navigator

    @classmethod
    def from_api(
        cls, raw: dict[str, Any], *, node_id: int | None, vertical: Vertical = MARKETPLACE
    ) -> NodeView:
        categories: list[Category] = []
        filters: list[Filter] = []
        for group in raw.get("navigatorGroups", []):
            for nav in group.get("navigatorList", []):
                if nav.get("id") == vertical.category_nav:
                    categories.extend(_parse_categories(nav))
                else:
                    filters.append(_parse_filter(nav))
        return cls(
            node_id=node_id,
            vertical=vertical,
            rows_found=raw.get("rowsFound", 0),
            breadcrumbs=tuple(_parse_breadcrumbs(raw.get("breadcrumbs", []))),
            categories=tuple(categories),
            filters=tuple(filters),
        )


def navigate(
    node: int | None = None,
    *,
    vertical: Vertical = MARKETPLACE,
    selections: QueryParams | None = None,
    client: WillhabenClient | None = None,
) -> NodeView:
    """Fetch a catalog node and return its child categories and valid filters.

    `node` is the vertical's category id (or `None` for the vertical root).
    `selections` is a flat param dict forwarded so the response reflects
    dependent filters (e.g. pass a chosen make to populate auto `model`).
    Performs one `rows=1` live request. `rows` is always pinned to 1.
    """
    client = client or WillhabenClient()
    path, node_params = _target(vertical, node)
    params: dict[str, QueryValue] = {**node_params}
    if selections:
        params.update(selections)
    params["rows"] = 1  # discovery request: never let selections override it
    return NodeView.from_api(client.search(path, params), node_id=node, vertical=vertical)
