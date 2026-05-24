from __future__ import annotations

import httpx
import pytest

from willhaben import (
    AREAS,
    RealEstateCategory,
    count,
    count_realestate,
)
from willhaben.constants import (
    API_ROOT,
    AREAS_BY_ID,
    DEFAULT_USER_AGENT,
    MARKETPLACE_PATH,
    X_WH_CLIENT,
)


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
        "X-WH-Client": X_WH_CLIENT,
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json",
    }
    params = {
        "rows": 1,
        "areaId": [1, 2, 3, 4, 5, 6, 7, 8, 900, 22000],
    }
    url = f"{API_ROOT}/{MARKETPLACE_PATH}"
    with httpx.Client(http2=True, timeout=30) as client:
        resp = client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
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
