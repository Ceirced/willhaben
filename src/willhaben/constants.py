from __future__ import annotations

from enum import IntEnum
from typing import Final

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

AREAS: Final[dict[str, int]] = {
    "wien": 9,
    "niederösterreich": 3,
    "oberösterreich": 4,
    "salzburg": 5,
    "tirol": 7,
    "vorarlberg": 8,
    "kärnten": 2,
    "steiermark": 6,
    "burgenland": 1,
}


class SortOrder(IntEnum):
    NEWEST = 1
    DISTANCE = 2
    PRICE_ASC = 3
    PRICE_DESC = 4
    RELEVANCE = 7
