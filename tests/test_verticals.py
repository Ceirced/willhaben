from __future__ import annotations

import pytest

from willhaben.verticals import AUTO, MARKETPLACE, REALESTATE, _target


class TestTarget:
    def test_marketplace_root_is_bare_path(self) -> None:
        assert _target(MARKETPLACE, None) == (
            "atz/seo/kaufen-und-verkaufen/marktplatz",
            {},
        )

    def test_marketplace_node_is_query_param(self) -> None:
        assert _target(MARKETPLACE, 2724) == (
            "atz/seo/kaufen-und-verkaufen/marktplatz",
            {"ATTRIBUTE_TREE": 2724},
        )

    def test_realestate_root_path(self) -> None:
        assert _target(REALESTATE, None) == ("atz/seo/immobilien/immobilien", {})

    def test_realestate_node_in_path(self) -> None:
        assert _target(REALESTATE, 102) == ("atz/2/102", {})

    def test_auto_root_path(self) -> None:
        assert _target(AUTO, None) == ("atz/seo/gebrauchtwagen/auto", {})

    def test_auto_node_unsupported_raises(self) -> None:
        with pytest.raises(ValueError, match="auto"):
            _target(AUTO, 4)

    def test_category_nav_names(self) -> None:
        assert MARKETPLACE.category_nav == "category"
        assert REALESTATE.category_nav == "searchId"
        assert AUTO.category_nav == "searchId"
