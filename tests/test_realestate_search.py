from __future__ import annotations

from typing import Any

from willhaben.constants import SortOrder
from willhaben.realestate import (
    RealEstateCategory,
    _build_realestate_params,
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
            client=client,  # type: ignore[arg-type]
        )
        assert result.rows_found == 42
        assert len(result.ads) == 1
        assert result.ads[0].id == "1"

    def test_uses_category_in_path(self) -> None:
        client = StubClient([make_response(rows_found=0)])
        search_realestate(
            category=RealEstateCategory.HOUSE_BUY,
            client=client,  # type: ignore[arg-type]
        )
        assert client.paths[0] == "atz/2/102"

    def test_passes_filters(self) -> None:
        client = StubClient([make_response(rows_found=0)])
        search_realestate(
            category=RealEstateCategory.APARTMENT_RENT,
            keyword="garten",
            price_to=1500,
            rooms="2X3",
            client=client,  # type: ignore[arg-type]
        )
        assert client.calls[0]["keyword"] == "garten"
        assert client.calls[0]["PRICE_TO"] == 1500
        assert client.calls[0]["NO_OF_ROOMS_BUCKET"] == "2X3"
