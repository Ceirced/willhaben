from __future__ import annotations

from .client import WillhabenAPIError, WillhabenClient
from .constants import AREAS, AREAS_BY_ID, MAX_ROWS_PER_PAGE, Area, SortOrder
from .models import Ad, SearchResult
from .realestate import (
    RealEstateAd,
    RealEstateCategory,
    RealEstateSearchResult,
    count_realestate,
    iter_realestate_ads,
    search_realestate,
)
from .search import count, iter_ads, search

__all__ = [
    "AREAS",
    "AREAS_BY_ID",
    "MAX_ROWS_PER_PAGE",
    "Ad",
    "Area",
    "RealEstateAd",
    "RealEstateCategory",
    "RealEstateSearchResult",
    "SearchResult",
    "SortOrder",
    "WillhabenAPIError",
    "WillhabenClient",
    "count",
    "count_realestate",
    "iter_ads",
    "iter_realestate_ads",
    "search",
    "search_realestate",
]
