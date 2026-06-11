from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from willhaben.navigation import Filter, FilterType, FilterValue, NodeView, Order, SelectionMode, navigate
from willhaben.verticals import AUTO, MARKETPLACE, REALESTATE

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class StubClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def search(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.paths.append(path)
        self.calls.append(params)
        return self.responses.pop(0)


class TestParseRoot:
    def test_lists_top_level_categories(self) -> None:
        view = NodeView.from_api(load("navigate_root.json"), node_id=None)
        labels = {c.label for c in view.categories}
        assert "Smartphones / Telefonie" in labels
        assert len(view.categories) >= 15


class TestParseApple:
    def test_lists_iphone_17_pro_child(self) -> None:
        view = NodeView.from_api(load("navigate_apple.json"), node_id=2724)
        by_id = {c.id: c.label for c in view.categories}
        assert by_id.get(5015997) == "iPhone 17 Pro"

    def test_breadcrumb_roots_have_no_node_id(self) -> None:
        view = NodeView.from_api(load("navigate_apple.json"), node_id=2724)
        assert view.breadcrumbs[0].node_id is None  # "Startseite"
        assert any(c.node_id == 2724 for c in view.breadcrumbs)


class TestParseLeaf:
    def test_leaf_has_no_child_categories(self) -> None:
        view = NodeView.from_api(load("navigate_iphone.json"), node_id=5015997)
        assert view.categories == ()

    def test_storage_filter_is_multi_select_tree_attribute(self) -> None:
        view = NodeView.from_api(load("navigate_iphone.json"), node_id=5015997)
        storage = next(f for f in view.filters if f.label == "Speicherkapazität")
        assert storage.params == ("treeAttributes",)
        assert storage.selection == SelectionMode.MULTI
        assert storage.values  # non-empty
        assert storage.values[0].value  # each value carries its tree id

    def test_price_filter_is_a_range(self) -> None:
        view = NodeView.from_api(load("navigate_iphone.json"), node_id=5015997)
        price = next(f for f in view.filters if "PRICE_FROM" in f.params)
        assert price.type == FilterType.RANGE
        assert price.params == ("PRICE_FROM", "PRICE_TO")

    def test_a_single_select_filter_is_parsed(self) -> None:
        view = NodeView.from_api(load("navigate_iphone.json"), node_id=5015997)
        single = next(f for f in view.filters if f.selection == SelectionMode.SINGLE)
        assert single.selection == SelectionMode.SINGLE


class TestEmptyResponse:
    def test_missing_navigator_groups_yields_empty_tuples(self) -> None:
        view = NodeView.from_api({"rowsFound": 0}, node_id=None)
        assert view.categories == ()
        assert view.filters == ()
        assert view.breadcrumbs == ()
        assert view.rows_found == 0
        assert view.vertical is MARKETPLACE


class TestNavigateRequest:
    def test_marketplace_node_query_param(self) -> None:
        stub = StubClient([load("navigate_apple.json")])
        view = navigate(2724, client=stub)  # ty: ignore[invalid-argument-type]
        assert stub.paths == ["atz/seo/kaufen-und-verkaufen/marktplatz"]
        assert stub.calls[0]["ATTRIBUTE_TREE"] == 2724
        assert stub.calls[0]["rows"] == 1
        assert view.vertical is MARKETPLACE

    def test_realestate_root_path_no_node(self) -> None:
        stub = StubClient([load("navigate_apple.json")])
        navigate(vertical=REALESTATE, client=stub)  # ty: ignore[invalid-argument-type]
        assert stub.paths == ["atz/seo/immobilien/immobilien"]

    def test_marketplace_root_omits_attribute_tree(self) -> None:
        stub = StubClient([load("navigate_root.json")])
        navigate(client=stub)  # ty: ignore[invalid-argument-type]
        assert "ATTRIBUTE_TREE" not in stub.calls[0]

    def test_selections_are_forwarded(self) -> None:
        stub = StubClient([load("navigate_apple.json")])
        navigate(vertical=AUTO, selections={"CAR_MODEL/MAKE": 1005}, client=stub)  # ty: ignore[invalid-argument-type]
        assert stub.calls[0]["rows"] == 1
        assert stub.calls[0]["CAR_MODEL/MAKE"] == 1005


class TestOrder:
    def test_order_holds_vertical_node_params(self) -> None:
        order = Order(MARKETPLACE, 2724, {"PRICE_TO": 900})
        assert order.vertical is MARKETPLACE
        assert order.node == 2724
        assert order.params == {"PRICE_TO": 900}


class TestPublicApi:
    def test_navigation_symbols_are_exported(self) -> None:
        import willhaben

        for name in (
            "navigate",
            "NodeView",
            "Category",
            "Filter",
            "FilterValue",
            "Crumb",
            "FilterType",
            "SelectionMode",
        ):
            assert hasattr(willhaben, name), name


class TestFilterValueParams:
    def test_value_property_returns_first_param_value(self) -> None:
        fv = FilterValue(label="256 GB", params={"treeAttributes": "2537"}, hits=10)
        assert fv.value == "2537"

    def test_bucketed_range_keeps_both_bounds(self) -> None:
        fv = FilterValue(
            label="10.000 – 49.999",
            params={"MILEAGE_FROM": "10000", "MILEAGE_TO": "49999"},
            hits=5,
        )
        assert fv.params["MILEAGE_FROM"] == "10000"
        assert fv.params["MILEAGE_TO"] == "49999"


class TestFilterAvailable:
    def test_default_available_true(self) -> None:
        f = Filter(
            id="x", label="X", params=("p",), type=FilterType.SELECT,
            selection=SelectionMode.SINGLE, values=(), available=True,
        )
        assert f.available is True

    def test_not_selectable_sets_available_false(self) -> None:
        from willhaben.navigation import _parse_filter

        f = _parse_filter({"id": "model", "label": "Model", "navigatorType": "NOT_SELECTABLE"})
        assert f.available is False
        assert f.values == ()


class TestParseMarketplace:
    def test_categories_from_category_navigator(self) -> None:
        view = NodeView.from_api(
            load("navigate_apple.json"), node_id=2724, vertical=MARKETPLACE
        )
        assert view.vertical is MARKETPLACE
        by_id = {c.id: c.label for c in view.categories}
        assert by_id.get(5015997) == "iPhone 17 Pro"

    def test_storage_filter_values_carry_params(self) -> None:
        view = NodeView.from_api(
            load("navigate_iphone.json"), node_id=5015997, vertical=MARKETPLACE
        )
        storage = next(f for f in view.filters if f.id == "Speicherkapazität")
        assert storage.selection is SelectionMode.MULTI
        assert all("treeAttributes" in v.params for v in storage.values)
