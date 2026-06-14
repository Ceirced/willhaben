from __future__ import annotations

from typing import Any

from willhaben.constants import SortOrder
from willhaben.navigation import Order
from willhaben.search import count, iter_ads, search
from willhaben.verticals import MARKETPLACE, REALESTATE


class StubClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def search(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.paths.append(path)
        self.calls.append(params)
        return self.responses.pop(0)


def make_response(*, rows_found: int, ads: list[dict[str, Any]] | None = None, page: int = 1) -> dict[str, Any]:
    ads = ads or []
    return {
        "rowsFound": rows_found,
        "rowsReturned": len(ads),
        "pageRequested": page,
        "advertSummaryList": {"advertSummary": ads},
    }


def make_ad(ad_id: str = "1") -> dict[str, Any]:
    return {"id": ad_id, "description": f"ad {ad_id}", "attributes": {"attribute": []}}


class TestSearchExecutesOrder:
    def test_marketplace_order_routes_with_params(self) -> None:
        client = StubClient([make_response(rows_found=5, ads=[make_ad(str(i)) for i in range(5)])])
        order = Order(MARKETPLACE, 2724, {"PRICE_TO": 900})
        result = search(order, client=client)  # ty: ignore[invalid-argument-type]
        assert client.paths == ["atz/seo/kaufen-und-verkaufen/marktplatz"]
        assert client.calls[0]["ATTRIBUTE_TREE"] == 2724
        assert client.calls[0]["PRICE_TO"] == 900
        assert result.rows_found == 5

    def test_realestate_order_uses_path_node(self) -> None:
        client = StubClient([make_response(rows_found=0)])
        count(Order(REALESTATE, 102, {}), client=client)  # ty: ignore[invalid-argument-type]
        assert client.paths == ["atz/2/102"]

    def test_sort_only_on_search(self) -> None:
        client = StubClient([make_response(rows_found=1, ads=[make_ad("1")])])
        search(Order(MARKETPLACE, None, {}), sort=SortOrder.PRICE_ASC, client=client)  # ty: ignore[invalid-argument-type]
        assert client.calls[0]["sort"] == int(SortOrder.PRICE_ASC)


class TestCount:
    def test_returns_rows_found(self) -> None:
        client = StubClient([make_response(rows_found=99)])
        assert count(Order(MARKETPLACE, None, {}), client=client) == 99  # ty: ignore[invalid-argument-type]

    def test_uses_rows_one(self) -> None:
        client = StubClient([make_response(rows_found=99)])
        count(Order(MARKETPLACE, None, {}), client=client)  # ty: ignore[invalid-argument-type]
        assert client.calls[0]["rows"] == 1


class TestIterAds:
    def _order(self) -> Order:
        return Order(MARKETPLACE, None, {})

    def test_yields_all_pages(self) -> None:
        ads_p1 = [make_ad(str(i)) for i in range(200)]
        ads_p2 = [make_ad(str(i)) for i in range(200, 400)]
        client = StubClient([
            make_response(rows_found=400, ads=ads_p1, page=1),
            make_response(rows_found=400, ads=ads_p2, page=2),
        ])
        result = list(iter_ads(self._order(), client=client))  # ty: ignore[invalid-argument-type]
        assert len(result) == 400
        assert result[0].id == "0"
        assert result[-1].id == "399"
        assert client.calls[0]["page"] == 1
        assert client.calls[1]["page"] == 2

    def test_stops_at_max_results(self) -> None:
        ads = [make_ad(str(i)) for i in range(200)]
        client = StubClient([make_response(rows_found=400, ads=ads)])
        result = list(iter_ads(self._order(), max_results=5, client=client))  # ty: ignore[invalid-argument-type]
        assert len(result) == 5

    def test_stops_when_rows_found_reached(self) -> None:
        ads = [make_ad(str(i)) for i in range(3)]
        client = StubClient([make_response(rows_found=3, ads=ads)])
        result = list(iter_ads(self._order(), client=client))  # ty: ignore[invalid-argument-type]
        assert len(result) == 3
        assert len(client.calls) == 1

    def test_stops_on_empty_page(self) -> None:
        client = StubClient([make_response(rows_found=999, ads=[])])
        result = list(iter_ads(self._order(), client=client))  # ty: ignore[invalid-argument-type]
        assert result == []
