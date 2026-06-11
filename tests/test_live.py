from __future__ import annotations

import httpx
import pytest

from willhaben import AUTO, MARKETPLACE, REALESTATE, count, navigate
from willhaben.constants import (
    API_ROOT,
    AREAS_BY_ID,
    DEFAULT_USER_AGENT,
    MARKETPLACE_PATH,
    X_WH_CLIENT,
)


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
    """Detect drift between the committed area tree and the live API."""
    live_pairs = _fetch_live_pairs()
    local_pairs = {
        (area.id, child.id)
        for area in AREAS_BY_ID.values()
        for child in area.children
    }
    assert not (live_pairs - local_pairs), f"new in API: {live_pairs - local_pairs}"
    assert not (local_pairs - live_pairs), f"removed from API: {local_pairs - live_pairs}"


@pytest.mark.live
def test_live_navigate_root_lists_known_categories() -> None:
    view = navigate()
    labels = {c.label for c in view.categories}
    assert "Smartphones / Telefonie" in labels
    assert len(view.categories) >= 15


@pytest.mark.live
def test_live_navigate_reaches_iphone_leaf() -> None:
    view = navigate(2724)
    assert any(c.id == 5015997 for c in view.categories)


@pytest.mark.live
def test_live_marketplace_node_scopes_via_attribute_tree() -> None:
    """Guards the categoryId-class bug: ATTRIBUTE_TREE scoping must reduce the count."""
    assert count(navigate(2691, vertical=MARKETPLACE).order()) < count(
        navigate(vertical=MARKETPLACE).order()
    )


@pytest.mark.live
def test_live_marketplace_category_filter_reduces_count() -> None:
    apple = navigate(2724, vertical=MARKETPLACE)
    storage = next(f for f in apple.filters if f.id == "Speicherkapazität")
    filtered = count(apple.order(select={storage.label: [storage.values[0].label]}))
    assert filtered < apple.rows_found


@pytest.mark.live
def test_live_realestate_search_id_scopes_via_path() -> None:
    view = navigate(vertical=REALESTATE)
    by_label = {c.label: c.id for c in view.categories}
    assert by_label.get("Haus kaufen") == 102
    scoped = count(navigate(102, vertical=REALESTATE).order())
    root = count(navigate(vertical=REALESTATE).order())
    assert scoped < root


@pytest.mark.live
def test_live_search_id_as_param_does_not_scope() -> None:
    """The categoryId-class trap: searchId as a query param is ignored, so it
    returns everything (far more than the path-scoped Haus-kaufen node)."""
    root = navigate(vertical=REALESTATE)
    param_count = count(root.order(extra={"searchId": 102}))
    path_count = count(navigate(102, vertical=REALESTATE).order())
    assert param_count > path_count


@pytest.mark.live
def test_live_auto_model_unlocks_after_make() -> None:
    locked = next(f for f in navigate(vertical=AUTO).filters if f.id == "model")
    assert locked.available is False
    unlocked = next(
        f
        for f in navigate(vertical=AUTO, selections={"CAR_MODEL/MAKE": 1005}).filters
        if f.id == "model"
    )
    assert unlocked.available is True
