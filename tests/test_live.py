from __future__ import annotations

import json
import urllib.parse
import urllib.request

import pytest

from willhaben import (
    AREAS,
    RealEstateCategory,
    count,
    count_realestate,
)
from willhaben.constants import AREAS_BY_ID


@pytest.mark.live
def test_live_count_returns_positive() -> None:
    """Smoke test: keyword 'fahrrad' should always have results on willhaben.at."""
    assert count(keyword="fahrrad") > 0


@pytest.mark.live
def test_live_realestate_count_returns_positive() -> None:
    """Smoke test: rental flats in Vienna should always have results."""
    result = count_realestate(
        category=RealEstateCategory.APARTMENT_RENT,
        area_id=AREAS["wien"].id,
    )
    assert result > 0


def _fetch_live_pairs() -> set[tuple[int, int]]:
    headers = {
        "X-WH-Client": "api@willhaben.at;responsive_web;server;1.0.0;desktop",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    qs = urllib.parse.urlencode(
        [("rows", "1")]
        + [("areaId", str(i)) for i in (1, 2, 3, 4, 5, 6, 7, 8, 900, 22000)]
    )
    url = (
        "https://www.willhaben.at/webapi/iad/search/atz/seo/"
        f"kaufen-und-verkaufen/marktplatz?{qs}"
    )
    req = urllib.request.Request(url, headers=headers)  # noqa: S310
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        payload = json.loads(resp.read())
    pairs: set[tuple[int, int]] = set()
    for grp in payload.get("navigatorGroups", []):
        for nav in grp.get("navigatorList", []):
            if nav.get("id") != "district":
                continue
            for gpv in nav.get("groupedPossibleValues", []):
                for pv in gpv.get("possibleValues", []):
                    parent = pv.get("parent") or {}
                    pid = next(
                        (
                            int(u["value"])
                            for u in parent.get("urlParamRepresentationForValue", [])
                            if u.get("urlParameterName") == "areaId"
                        ),
                        None,
                    )
                    cid = next(
                        (
                            int(u["value"])
                            for u in pv.get("urlParamRepresentationForValue", [])
                            if u.get("urlParameterName") == "areaId"
                        ),
                        None,
                    )
                    if pid is not None and cid is not None:
                        pairs.add((pid, cid))
    return pairs


@pytest.mark.live
def test_live_areas_match_committed_tree() -> None:
    """Detect drift between the committed area tree and the live API.

    If this fails, hand-edit `src/willhaben/_areas_data.py` to match the
    live API and update the hardcoded count in `tests/test_areas.py` if
    needed.
    """
    live_pairs = _fetch_live_pairs()
    local_pairs = {
        (area.id, child.id)
        for area in AREAS_BY_ID.values()
        for child in area.children
    }
    missing_locally = live_pairs - local_pairs
    extra_locally = local_pairs - live_pairs
    assert not missing_locally, f"new in API: {missing_locally}"
    assert not extra_locally, f"removed from API: {extra_locally}"
