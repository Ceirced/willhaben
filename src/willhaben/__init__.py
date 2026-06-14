from __future__ import annotations

from .client import WillhabenAPIError, WillhabenClient
from .constants import AREAS, AREAS_BY_ID, MAX_ROWS_PER_PAGE, Area, SortOrder
from .models import Ad, SearchResult
from .navigation import (
    Category,
    Crumb,
    Filter,
    FilterType,
    FilterValue,
    NodeView,
    Order,
    SelectionMode,
    navigate,
)
from .search import count, iter_ads, search
from .verticals import AUTO, MARKETPLACE, REALESTATE, Vertical

__all__ = [
    "AREAS",
    "AREAS_BY_ID",
    "AUTO",
    "MARKETPLACE",
    "MAX_ROWS_PER_PAGE",
    "REALESTATE",
    "Ad",
    "Area",
    "Category",
    "Crumb",
    "Filter",
    "FilterType",
    "FilterValue",
    "NodeView",
    "Order",
    "SearchResult",
    "SelectionMode",
    "SortOrder",
    "Vertical",
    "WillhabenAPIError",
    "WillhabenClient",
    "count",
    "iter_ads",
    "navigate",
    "search",
]
