from __future__ import annotations

import json
from pathlib import Path

from willhaben.navigation import FilterType, NodeView, SelectionMode

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


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
