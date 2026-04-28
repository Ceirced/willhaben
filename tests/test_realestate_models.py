from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from willhaben.realestate import (
    REAL_ESTATE_AREAS,
    RealEstateAd,
    RealEstateCategory,
    RealEstateSearchResult,
)


class TestRealEstateCategory:
    def test_apartment_rent_value(self) -> None:
        assert RealEstateCategory.APARTMENT_RENT == 131

    def test_house_buy_value(self) -> None:
        assert RealEstateCategory.HOUSE_BUY == 102

    def test_all_value(self) -> None:
        assert RealEstateCategory.ALL == 90


class TestRealEstateAreas:
    def test_wien_matches_marketplace(self) -> None:
        assert REAL_ESTATE_AREAS["wien"] == 900

    def test_burgenland_differs_from_marketplace(self) -> None:
        # Marketplace uses 100, real estate uses 1.
        assert REAL_ESTATE_AREAS["burgenland"] == 1


class TestRealEstateAdFromApi:
    def test_full_apartment_fields(self, load_fixture) -> None:
        raw = load_fixture("realestate_response.json")
        ad = RealEstateAd.from_api(raw["advertSummaryList"]["advertSummary"][0])
        assert ad.id == "940426115"
        assert ad.title == "Ruhige Wohnung am See"
        assert ad.price == Decimal("1200")
        assert ad.price_display == "€ 1.200"
        assert ad.location == "Seeboden"
        assert ad.postcode == "9871"
        assert ad.district == "Spittal an der Drau"
        assert ad.state == "Kärnten"
        assert ad.coordinates == (46.82335, 13.521889)
        assert ad.published_at == datetime(2026, 4, 28, 22, 19, 0, tzinfo=UTC)
        assert ad.rooms == 2
        assert ad.area_m2 == Decimal("60")
        assert ad.property_type == "Wohnung"
        assert ad.property_type_id == 3
        assert ad.free_area_type == "Loggia"
        assert ad.is_private is True
        assert ad.main_image_url == "https://images.willhaben.at/940/426/115_main.jpg"
        assert ad.url == "https://www.willhaben.at/iad/share/940426115"
        assert (
            ad.seo_url
            == "https://www.willhaben.at/iad/immobilien/d/mietwohnungen/"
            "kaernten/spittal-an-der-drau/ruhige-wohnung-am-see"
        )
        assert "RENT/PER_MONTH_LETTINGS" in ad.raw_attributes

    def test_sparse_plot_tolerates_missing_fields(
        self, load_fixture
    ) -> None:
        raw = load_fixture("realestate_response.json")
        ad = RealEstateAd.from_api(raw["advertSummaryList"]["advertSummary"][1])
        assert ad.id == "999111222"
        assert ad.price is None
        assert ad.price_display == "Preis auf Anfrage"
        assert ad.rooms is None
        assert ad.area_m2 == Decimal("1500.5")
        assert ad.property_type is None
        assert ad.free_area_type is None
        assert ad.coordinates is None
        assert ad.main_image_url is None
        assert ad.is_private is False
        assert ad.url == "https://www.willhaben.at/iad/object?adId=999111222"

    def test_minimal_ad(self) -> None:
        ad = RealEstateAd.from_api({"id": 1, "attributes": {"attribute": []}})
        assert ad.id == "1"
        assert ad.title == ""
        assert ad.price is None
        assert ad.rooms is None
        assert ad.is_private is False

    def test_parse_int_handles_zero(self) -> None:
        ad = RealEstateAd.from_api(
            {
                "id": 1,
                "attributes": {
                    "attribute": [
                        {"name": "NUMBER_OF_ROOMS", "values": ["0"]},
                        {"name": "PROPERTY_TYPE_ID", "values": ["0"]},
                    ]
                },
            }
        )
        assert ad.rooms == 0
        assert ad.property_type_id == 0


class TestRealEstateSearchResult:
    def test_basic(self, load_fixture) -> None:
        result = RealEstateSearchResult.from_api(
            load_fixture("realestate_response.json")
        )
        assert result.rows_found == 7269
        assert result.rows_returned == 2
        assert result.page == 1
        assert len(result.ads) == 2
        assert result.ads[0].id == "940426115"

    def test_empty_response(self) -> None:
        result = RealEstateSearchResult.from_api({})
        assert result.rows_found == 0
        assert result.rows_returned == 0
        assert result.page == 1
        assert result.ads == []
