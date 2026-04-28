from __future__ import annotations

from typing import Any

from willhaben.constants import SortOrder
from willhaben.search import _build_params, count, iter_ads, search


class StubClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, str | int]] = []
        self.paths: list[str] = []

    def search(
        self, path: str, params: dict[str, str | int]
    ) -> dict[str, Any]:
        self.paths.append(path)
        self.calls.append(params)
        return self.responses.pop(0)


def make_response(
    *,
    rows_found: int,
    ads: list[dict[str, Any]] | None = None,
    page: int = 1,
) -> dict[str, Any]:
    ads = ads or []
    return {
        "rowsFound": rows_found,
        "rowsReturned": len(ads),
        "pageRequested": page,
        "advertSummaryList": {"advertSummary": ads},
    }


def make_ad(ad_id: str = "1") -> dict[str, Any]:
    return {
        "id": ad_id,
        "description": f"ad {ad_id}",
        "attributes": {"attribute": []},
    }


class TestBuildParams:
    def test_minimal(self) -> None:
        params = _build_params(
            keyword=None,
            price_from=None,
            price_to=None,
            area_id=None,
            category_id=None,
            is_private=None,
            sort=None,
            rows=10,
            page=1,
            extra=None,
        )
        assert params == {"rows": 10, "page": 1}

    def test_all_options(self) -> None:
        params = _build_params(
            keyword="bike",
            price_from=10,
            price_to=200,
            area_id=900,
            category_id=42,
            is_private=True,
            sort=SortOrder.NEWEST,
            rows=30,
            page=2,
            extra={"FOO": "bar"},
        )
        assert params == {
            "rows": 30,
            "page": 2,
            "keyword": "bike",
            "PRICE_FROM": 10,
            "PRICE_TO": 200,
            "areaId": 900,
            "categoryId": 42,
            "ISPRIVATE": 1,
            "sort": 1,
            "FOO": "bar",
        }

    def test_is_private_false_omitted(self) -> None:
        params = _build_params(
            keyword=None,
            price_from=None,
            price_to=None,
            area_id=None,
            category_id=None,
            is_private=False,
            sort=None,
            rows=10,
            page=1,
            extra=None,
        )
        assert "ISPRIVATE" not in params

    def test_sort_int(self) -> None:
        params = _build_params(
            keyword=None,
            price_from=None,
            price_to=None,
            area_id=None,
            category_id=None,
            is_private=None,
            sort=4,
            rows=10,
            page=1,
            extra=None,
        )
        assert params["sort"] == 4

    def test_extra_overrides(self) -> None:
        params = _build_params(
            keyword="bike",
            price_from=None,
            price_to=None,
            area_id=None,
            category_id=None,
            is_private=None,
            sort=None,
            rows=10,
            page=1,
            extra={"keyword": "car"},
        )
        assert params["keyword"] == "car"


class TestSearch:
    def test_returns_search_result(self) -> None:
        client = StubClient([make_response(rows_found=1, ads=[make_ad("1")])])
        result = search(keyword="x", client=client)  # type: ignore[arg-type]
        assert result.rows_found == 1
        assert len(result.ads) == 1
        assert result.ads[0].id == "1"

    def test_passes_params(self) -> None:
        client = StubClient([make_response(rows_found=0)])
        search(keyword="bike", price_to=100, client=client)  # type: ignore[arg-type]
        assert client.calls[0]["keyword"] == "bike"
        assert client.calls[0]["PRICE_TO"] == 100


class TestCount:
    def test_returns_rows_found(self) -> None:
        client = StubClient([make_response(rows_found=99)])
        assert count(keyword="x", client=client) == 99  # type: ignore[arg-type]

    def test_uses_rows_one(self) -> None:
        client = StubClient([make_response(rows_found=99)])
        count(keyword="x", client=client)  # type: ignore[arg-type]
        assert client.calls[0]["rows"] == 1


class TestIterAds:
    def test_yields_all_pages(self) -> None:
        ads_p1 = [make_ad(str(i)) for i in range(200)]
        ads_p2 = [make_ad(str(i)) for i in range(200, 400)]
        client = StubClient(
            [
                make_response(rows_found=400, ads=ads_p1, page=1),
                make_response(rows_found=400, ads=ads_p2, page=2),
            ]
        )
        result = list(iter_ads(client=client))  # type: ignore[arg-type]
        assert len(result) == 400
        assert result[0].id == "0"
        assert result[-1].id == "399"

    def test_stops_at_max_results(self) -> None:
        ads = [make_ad(str(i)) for i in range(200)]
        client = StubClient([make_response(rows_found=400, ads=ads)])
        result = list(iter_ads(max_results=5, client=client))  # type: ignore[arg-type]
        assert len(result) == 5

    def test_stops_when_rows_found_reached(self) -> None:
        ads = [make_ad(str(i)) for i in range(3)]
        client = StubClient([make_response(rows_found=3, ads=ads)])
        result = list(iter_ads(client=client))  # type: ignore[arg-type]
        assert len(result) == 3
        assert len(client.calls) == 1

    def test_stops_on_empty_page(self) -> None:
        client = StubClient([make_response(rows_found=999, ads=[])])
        result = list(iter_ads(client=client))  # type: ignore[arg-type]
        assert result == []
