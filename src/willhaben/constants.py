from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Final

from ._areas_data import AREAS_DATA

API_ROOT: Final = "https://www.willhaben.at/webapi/iad/search"

# Marketplace endpoint path (joined onto API_ROOT).
MARKETPLACE_PATH: Final = "atz/seo/kaufen-und-verkaufen/marktplatz"

# Without this header the same endpoint returns 400 with an empty body.
X_WH_CLIENT: Final = "api@willhaben.at;responsive_web;server;1.0.0;desktop"

DEFAULT_USER_AGENT: Final = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Server silently caps `rows` at 200 even if you request more.
MAX_ROWS_PER_PAGE: Final = 200

@dataclass(slots=True, eq=False)
class Area:
    """A willhaben area: a Bundesland, a district within one, or a country
    grouped under "andere Länder". `id` is the willhaben areaId (negative for
    foreign countries). Equality is by identity so the cyclic parent/child
    graph doesn't blow up `__eq__`.
    """

    id: int
    name: str
    parent: Area | None = field(default=None, repr=False)
    children: tuple[Area, ...] = ()


def _build_areas() -> tuple[dict[str, Area], dict[int, Area]]:
    by_slug: dict[str, Area] = {}
    by_id: dict[int, Area] = {}
    for state_id, state_name, child_data in AREAS_DATA:
        state = Area(id=state_id, name=state_name)
        children = tuple(
            Area(id=cid, name=cname, parent=state) for cid, cname in child_data
        )
        state.children = children
        by_id[state_id] = state
        by_slug[state_name.lower()] = state
        for child in children:
            by_id[child.id] = child
    return by_slug, by_id


_areas_by_slug, _areas_by_id = _build_areas()

AREAS: Final[dict[str, Area]] = _areas_by_slug
"""Top-level willhaben areas (Bundesländer + 'andere länder'), keyed by
lowercase German name. Each value is an `Area` whose `children` holds the
districts for Austrian states or the country list for 'andere länder'."""

AREAS_BY_ID: Final[dict[int, Area]] = _areas_by_id
"""Every node in the area tree, keyed by willhaben areaId. Use this to
resolve an areaId (e.g. from `SearchResult.counts_by_state`) back to its
`Area`. Includes the 10 top-level areas and all 138 children."""


class SortOrder(IntEnum):
    NEWEST = 1
    DISTANCE = 2
    PRICE_ASC = 3
    PRICE_DESC = 4
    RELEVANCE = 7
