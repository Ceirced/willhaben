from __future__ import annotations

from typing import Any

from willhaben.constants import SortOrder
from willhaben.realestate import (
    RealEstateCategory,
    _build_realestate_params,
    count_realestate,
    iter_realestate_ads,
    search_realestate,
)


class StubClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.paths: list[str] = []
        self.calls: list[dict[str, str | int]] = []

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


class TestBuildRealEstateParams:
    def test_minimal(self) -> None:
        params = _build_realestate_params(
            keyword=None,
            price_from=None,
            price_to=None,
            area_m2_from=None,
            area_m2_to=None,
            rooms=None,
            property_type=None,
            area_id=None,
            is_private=None,
            sort=None,
            rows=10,
            page=1,
            extra=None,
        )
        assert params == {"rows": 10, "page": 1}

    def test_all_options(self) -> None:
        params = _build_realestate_params(
            keyword="garten",
            price_from=500,
            price_to=1500,
            area_m2_from=50,
            area_m2_to=80,
            rooms="2X3",
            property_type=110,
            area_id=900,
            is_private=True,
            sort=SortOrder.NEWEST,
            rows=30,
            page=2,
            extra={"FOO": "bar"},
        )
        assert params == {
            "rows": 30,
            "page": 2,
            "keyword": "garten",
            "PRICE_FROM": 500,
            "PRICE_TO": 1500,
            "ESTATE_SIZE/LIVING_AREA_FROM": 50,
            "ESTATE_SIZE/LIVING_AREA_TO": 80,
            "NO_OF_ROOMS_BUCKET": "2X3",
            "PROPERTY_TYPE": 110,
            "areaId": 900,
            "ISPRIVATE": 1,
            "sort": 1,
            "FOO": "bar",
        }

    def test_is_private_false_omitted(self) -> None:
        params = _build_realestate_params(
            keyword=None,
            price_from=None,
            price_to=None,
            area_m2_from=None,
            area_m2_to=None,
            rooms=None,
            property_type=None,
            area_id=None,
            is_private=False,
            sort=None,
            rows=10,
            page=1,
            extra=None,
        )
        assert "ISPRIVATE" not in params

    def test_extra_overrides(self) -> None:
        params = _build_realestate_params(
            keyword="garten",
            price_from=None,
            price_to=None,
            area_m2_from=None,
            area_m2_to=None,
            rooms=None,
            property_type=None,
            area_id=None,
            is_private=None,
            sort=None,
            rows=10,
            page=1,
            extra={"keyword": "balkon"},
        )
        assert params["keyword"] == "balkon"


class TestSearchRealestate:
    def test_returns_search_result(self) -> None:
        client = StubClient([make_response(rows_found=42, ads=[make_ad("1")])])
        result = search_realestate(
            category=RealEstateCategory.APARTMENT_RENT,
            client=client,  # ty: ignore[invalid-argument-type]
        )
        assert result.rows_found == 42
        assert len(result.ads) == 1
        assert result.ads[0].id == "1"

    def test_uses_category_in_path(self) -> None:
        client = StubClient([make_response(rows_found=0)])
        search_realestate(
            category=RealEstateCategory.HOUSE_BUY,
            client=client,  # ty: ignore[invalid-argument-type]
        )
        assert client.paths[0] == "atz/2/102"

    def test_passes_filters(self) -> None:
        client = StubClient([make_response(rows_found=0)])
        search_realestate(
            category=RealEstateCategory.APARTMENT_RENT,
            keyword="garten",
            price_to=1500,
            rooms="2X3",
            client=client,  # ty: ignore[invalid-argument-type]
        )
        assert client.calls[0]["keyword"] == "garten"
        assert client.calls[0]["PRICE_TO"] == 1500
        assert client.calls[0]["NO_OF_ROOMS_BUCKET"] == "2X3"


class TestCountRealestate:
    def test_returns_rows_found(self) -> None:
        client = StubClient([make_response(rows_found=99)])
        assert (
            count_realestate(
                category=RealEstateCategory.APARTMENT_RENT,
                client=client,  # ty: ignore[invalid-argument-type]
            )
            == 99
        )

    def test_uses_rows_one(self) -> None:
        client = StubClient([make_response(rows_found=99)])
        count_realestate(
            category=RealEstateCategory.APARTMENT_RENT,
            client=client,  # ty: ignore[invalid-argument-type]
        )
        assert client.calls[0]["rows"] == 1


class TestIterRealestateAds:
    def test_yields_all_pages(self) -> None:
        ads_p1 = [make_ad(str(i)) for i in range(200)]
        ads_p2 = [make_ad(str(i)) for i in range(200, 400)]
        client = StubClient(
            [
                make_response(rows_found=400, ads=ads_p1, page=1),
                make_response(rows_found=400, ads=ads_p2, page=2),
            ]
        )
        result = list(
            iter_realestate_ads(
                category=RealEstateCategory.APARTMENT_RENT,
                client=client,  # ty: ignore[invalid-argument-type]
            )
        )
        assert len(result) == 400
        assert result[0].id == "0"
        assert result[-1].id == "399"

    def test_stops_at_max_results(self) -> None:
        ads = [make_ad(str(i)) for i in range(200)]
        client = StubClient([make_response(rows_found=400, ads=ads)])
        result = list(
            iter_realestate_ads(
                category=RealEstateCategory.APARTMENT_RENT,
                max_results=5,
                client=client,  # ty: ignore[invalid-argument-type]
            )
        )
        assert len(result) == 5

    def test_stops_when_rows_found_reached(self) -> None:
        ads = [make_ad(str(i)) for i in range(3)]
        client = StubClient([make_response(rows_found=3, ads=ads)])
        result = list(
            iter_realestate_ads(
                category=RealEstateCategory.APARTMENT_RENT,
                client=client,  # ty: ignore[invalid-argument-type]
            )
        )
        assert len(result) == 3
        assert len(client.calls) == 1

    def test_stops_on_empty_page(self) -> None:
        client = StubClient([make_response(rows_found=999, ads=[])])
        result = list(
            iter_realestate_ads(
                category=RealEstateCategory.APARTMENT_RENT,
                client=client,  # ty: ignore[invalid-argument-type]
            )
        )
        assert result == []
