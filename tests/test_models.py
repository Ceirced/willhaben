from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from willhaben.models import (
    Ad,
    SearchResult,
    _attrs_to_dict,
    _first,
    _parse_coords,
    _parse_price,
    _parse_published,
)


class TestParseHelpers:
    def test_first_returns_first(self) -> None:
        assert _first(["a", "b"]) == "a"

    def test_first_handles_none(self) -> None:
        assert _first(None) is None

    def test_first_handles_empty(self) -> None:
        assert _first([]) is None

    def test_attrs_to_dict(self) -> None:
        raw = [
            {"name": "X", "values": ["1", "2"]},
            {"name": "Y", "values": ["3"]},
        ]
        assert _attrs_to_dict(raw) == {"X": ["1", "2"], "Y": ["3"]}

    def test_parse_coords_valid(self) -> None:
        assert _parse_coords("48.2,16.3") == (48.2, 16.3)

    def test_parse_coords_none(self) -> None:
        assert _parse_coords(None) is None

    def test_parse_coords_empty(self) -> None:
        assert _parse_coords("") is None

    def test_parse_coords_malformed(self) -> None:
        assert _parse_coords("not,coords") is None

    def test_parse_coords_no_comma(self) -> None:
        assert _parse_coords("48.2") is None

    def test_parse_published_valid(self) -> None:
        result = _parse_published("1700000000000")
        assert result == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)

    def test_parse_published_none(self) -> None:
        assert _parse_published(None) is None

    def test_parse_published_invalid(self) -> None:
        assert _parse_published("not-a-number") is None

    def test_parse_price_valid(self) -> None:
        assert _parse_price("120.50") == Decimal("120.50")

    def test_parse_price_none(self) -> None:
        assert _parse_price(None) is None

    def test_parse_price_invalid(self) -> None:
        assert _parse_price("free") is None


class TestAdFromApi:
    def test_basic_fields(self, load_fixture) -> None:
        raw = load_fixture("search_response.json")
        ad_raw = raw["advertSummaryList"]["advertSummary"][0]
        ad = Ad.from_api(ad_raw)
        assert ad.id == "12345"
        assert ad.title == "Used Bicycle"
        assert ad.price == Decimal("120.00")
        assert ad.price_display == "€ 120,-"
        assert ad.location == "1010 Wien"
        assert ad.postcode == "1010"
        assert ad.district == "Innere Stadt"
        assert ad.state == "Wien"
        assert ad.coordinates == (48.2082, 16.3738)
        assert ad.published_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
        assert ad.body == "A nice used bicycle."
        assert ad.is_private is True
        assert ad.main_image_url == "https://images.willhaben.at/main.jpg"
        assert ad.url == "https://www.willhaben.at/iad/share/12345"
        assert ad.seo_url == "https://www.willhaben.at/iad/fahrraeder/used-bicycle"

    def test_url_falls_back_to_seo(self, load_fixture) -> None:
        raw = load_fixture("search_response.json")
        ad_raw = raw["advertSummaryList"]["advertSummary"][0]
        ad_raw["contextLinkList"] = {"contextLink": []}
        ad = Ad.from_api(ad_raw)
        assert ad.url == "https://www.willhaben.at/iad/fahrraeder/used-bicycle"

    def test_url_falls_back_to_object_id(self, load_fixture) -> None:
        raw = load_fixture("search_response.json")
        ad_raw = raw["advertSummaryList"]["advertSummary"][0]
        ad_raw["contextLinkList"] = {"contextLink": []}
        ad_raw["attributes"]["attribute"] = [
            a for a in ad_raw["attributes"]["attribute"] if a["name"] != "SEO_URL"
        ]
        ad = Ad.from_api(ad_raw)
        assert ad.url == "https://www.willhaben.at/iad/object?adId=12345"
        assert ad.seo_url is None

    def test_minimal_ad(self) -> None:
        ad = Ad.from_api({"id": 99, "attributes": {"attribute": []}})
        assert ad.id == "99"
        assert ad.title == ""
        assert ad.price is None
        assert ad.coordinates is None
        assert ad.is_private is False
        assert ad.main_image_url is None
        assert ad.url == "https://www.willhaben.at/iad/object?adId=99"

    def test_no_images(self, load_fixture) -> None:
        raw = load_fixture("search_response.json")
        ad_raw = raw["advertSummaryList"]["advertSummary"][0]
        ad_raw["advertImageList"] = {"advertImage": []}
        ad = Ad.from_api(ad_raw)
        assert ad.main_image_url is None

    def test_is_private_false_when_not_one(self, load_fixture) -> None:
        raw = load_fixture("search_response.json")
        ad_raw = raw["advertSummaryList"]["advertSummary"][0]
        for a in ad_raw["attributes"]["attribute"]:
            if a["name"] == "ISPRIVATE":
                a["values"] = ["0"]
        ad = Ad.from_api(ad_raw)
        assert ad.is_private is False


class TestSearchResultFromApi:
    def test_basic(self, load_fixture) -> None:
        result = SearchResult.from_api(load_fixture("search_response.json"))
        assert result.rows_found == 42
        assert result.rows_returned == 1
        assert result.page == 1
        assert len(result.ads) == 1
        assert result.ads[0].id == "12345"

    def test_empty_response(self) -> None:
        result = SearchResult.from_api({})
        assert result.rows_found == 0
        assert result.rows_returned == 0
        assert result.page == 1
        assert result.ads == []
