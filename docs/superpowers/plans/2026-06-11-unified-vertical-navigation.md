# Unified, data-driven vertical navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `willhaben` a single data-driven API where any vertical (marketplace, realestate, auto) is navigated, its categories and filters discovered at runtime, and a generic persistable `Order` (vertical + node + flat params) drives counting and ad fetching — with no domain-specific function arguments.

**Architecture:** A `Vertical` descriptor encodes the per-vertical request construction (root path, how a node is applied, which navigator holds categories). `navigate()` returns an immutable `NodeView` (categories + filters + breadcrumbs) parsed from one `rows=1` response. `NodeView.order(select=…, extra=…)` resolves human-readable selections against the discovered filters into an `Order`. `search`/`count`/`iter_ads` take only an `Order` plus mechanical kwargs. One generic `Ad`/`SearchResult` serves every vertical; vertical-specific fields live in `Ad.raw_attributes`.

**Tech Stack:** Python 3.13, httpx (HTTP/2), pytest. Spec: `docs/superpowers/specs/2026-06-11-unified-vertical-navigation-design.md`.

---

## File Structure

- **Create** `src/willhaben/verticals.py` — `Vertical` dataclass, `MARKETPLACE`/`REALESTATE`/`AUTO` constants, `_target(vertical, node)` request-target resolver.
- **Modify** `src/willhaben/navigation.py` — `FilterValue.params`, `Filter.available`, `NodeView.vertical`, category parsing via `vertical.category_nav`, `NOT_SELECTABLE` handling, `Order`, `navigate(vertical, selections)`, `NodeView.order/search/count`, `_resolve`.
- **Modify** `src/willhaben/models.py` — robust `Ad` price parsing; `SearchResult.node`; `counts_by_state` re-derivation; remove `_state_counts_from_raw`.
- **Rewrite** `src/willhaben/search.py` — `search/count/iter_ads` take an `Order`.
- **Delete** `src/willhaben/realestate.py` — folded into generic `Ad` + discovery.
- **Modify** `src/willhaben/__init__.py` — drop realestate exports; add `Vertical`, vertical constants, `Order`.
- **Modify** `pyproject.toml` — version `0.4.0` → `0.5.0` (0.x breaking change = minor bump).
- **Delete** `tests/test_realestate_search.py`, `tests/test_realestate_models.py`; **modify** `tests/test_navigation.py`, `tests/test_search.py`, `tests/test_models.py`, `tests/test_live.py`; **add** fixtures `navigate_realestate_root.json`, `navigate_realestate_other.json`, `navigate_auto.json`, `navigate_auto_bmw.json`.

Run the whole suite with `uv run pytest` (live tests are `-m live`, skipped by default). Run a single test with `uv run pytest tests/test_x.py::TestClass::test_name -v`.

---

## Task 1: `Vertical` descriptor and request-target resolver

**Files:**
- Create: `src/willhaben/verticals.py`
- Test: `tests/test_verticals.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verticals.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_verticals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'willhaben.verticals'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/willhaben/verticals.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vertical:
    """How to reach one willhaben vertical and read its categories.

    `root_path` is used when `node is None` (lists the vertical's categories).
    A node is applied either as `node_param` query param on `root_path`
    (marketplace) or by formatting `node_path` (realestate). `category_nav` is
    the navigator id whose values are the categories.
    """

    name: str
    root_path: str
    node_param: str | None
    node_path: str | None
    category_nav: str


MARKETPLACE = Vertical(
    "marketplace", "atz/seo/kaufen-und-verkaufen/marktplatz", "ATTRIBUTE_TREE", None, "category"
)
REALESTATE = Vertical(
    "realestate", "atz/seo/immobilien/immobilien", None, "atz/2/{node}", "searchId"
)
AUTO = Vertical("auto", "atz/seo/gebrauchtwagen/auto", None, None, "searchId")


def _target(vertical: Vertical, node: int | None) -> tuple[str, dict[str, int]]:
    """Resolve `(path, extra_query_params)` for a vertical + optional node."""
    if node is None:
        return vertical.root_path, {}
    if vertical.node_param is not None:
        return vertical.root_path, {vertical.node_param: node}
    if vertical.node_path is not None:
        return vertical.node_path.format(node=node), {}
    raise ValueError(f"{vertical.name} cannot scope to a node yet")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_verticals.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/willhaben/verticals.py tests/test_verticals.py
git commit -m "feat: add Vertical descriptor and request-target resolver"
```

---

## Task 2: `FilterValue.params` and `Filter.available`

The current `FilterValue` stores a single `value: str`, which cannot represent a bucketed range value (e.g. mileage carries both `MILEAGE_FROM` and `MILEAGE_TO`). Store the full URL representation instead, and add `available` to `Filter` for `NOT_SELECTABLE` filters.

**Files:**
- Modify: `src/willhaben/navigation.py`
- Test: `tests/test_navigation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_navigation.py — add at top-level
from willhaben.navigation import Filter, FilterValue


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_navigation.py::TestFilterValueParams -v`
Expected: FAIL — `FilterValue.__init__() got an unexpected keyword argument 'params'`.

- [ ] **Step 3: Edit the dataclasses and helpers in `src/willhaben/navigation.py`**

Replace the `FilterValue` dataclass:

```python
from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class FilterValue:
    label: str
    params: Mapping[str, str]   # this value's URL representation, e.g. {"treeAttributes": "2537"}
    hits: int | None

    @property
    def value(self) -> str | None:
        """The first param value — convenient for single-param discrete filters."""
        return next(iter(self.params.values()), None)
```

Add `available: bool` to the `Filter` dataclass (after `values`):

```python
@dataclass(frozen=True, slots=True)
class Filter:
    id: str
    label: str
    params: tuple[str, ...]
    type: FilterType
    selection: SelectionMode
    values: tuple[FilterValue, ...]
    available: bool
```

Replace `_url_value` with a helper that returns a value's full representation:

```python
def _value_params(value: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rep in value.get("urlParamRepresentationForValue") or []:
        name, raw = rep.get("urlParameterName"), rep.get("value")
        if name is not None and raw is not None:
            out[name] = str(raw)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_navigation.py::TestFilterValueParams tests/test_navigation.py::TestFilterAvailable -v`
Expected: PASS. (Other navigation tests will be red until Task 3 — that is expected.)

- [ ] **Step 5: Commit**

```bash
git add src/willhaben/navigation.py tests/test_navigation.py
git commit -m "feat: store full URL representation on FilterValue, add Filter.available"
```

---

## Task 3: Vertical-aware parsing (`searchId` categories, `NOT_SELECTABLE`, `NodeView.vertical`)

**Files:**
- Modify: `src/willhaben/navigation.py`
- Test: `tests/test_navigation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_navigation.py
from willhaben.verticals import MARKETPLACE, REALESTATE


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
```

(The realestate `searchId` and auto `NOT_SELECTABLE` assertions are added in Task 9 once those fixtures exist. This task makes the parser vertical-aware; the marketplace fixtures already exist.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_navigation.py::TestParseMarketplace -v`
Expected: FAIL — `NodeView.from_api() got an unexpected keyword argument 'vertical'`.

- [ ] **Step 3: Edit `src/willhaben/navigation.py`**

Add `NOT_SELECTABLE` awareness and rewrite the category/filter parsers and `NodeView`.

Replace `_parse_categories`:

```python
def _parse_categories(nav: dict[str, Any]) -> list[Category]:
    out: list[Category] = []
    for value in _iter_values(nav):
        params = _value_params(value)
        if not params:
            continue
        raw_id = next(iter(params.values()))
        out.append(
            Category(id=int(raw_id), label=value.get("label", ""), hits=value.get("hits"))
        )
    return out
```

Replace `_parse_filter`:

```python
def _parse_filter(nav: dict[str, Any]) -> Filter:
    url_info = nav.get("urlConstructionInformation") or {}
    params = tuple(
        p["urlParameterName"]
        for p in (url_info.get("urlParams") or [])
        if "urlParameterName" in p
    )
    values: list[FilterValue] = []
    for value in _iter_values(nav):
        vparams = _value_params(value)
        if not vparams:
            continue
        values.append(
            FilterValue(label=value.get("label", ""), params=vparams, hits=value.get("hits"))
        )
    nav_type = nav.get("navigatorType", "")
    return Filter(
        id=nav.get("id", ""),
        label=nav.get("label", ""),
        params=params,
        type=FilterType(_NAVIGATOR_TYPES.get(nav_type, "SELECT")),
        selection=(
            SelectionMode.MULTI
            if nav.get("navigatorSelectionType") == "MULTI_SELECT"
            else SelectionMode.SINGLE
        ),
        values=tuple(values),
        available=nav_type != "NOT_SELECTABLE",
    )
```

Add `vertical: Vertical` to `NodeView` and thread it through `from_api`:

```python
from .verticals import MARKETPLACE, Vertical, _target


@dataclass(frozen=True, slots=True)
class NodeView:
    node_id: int | None
    vertical: Vertical
    rows_found: int
    breadcrumbs: tuple[Crumb, ...]
    categories: tuple[Category, ...]
    filters: tuple[Filter, ...]

    @classmethod
    def from_api(
        cls, raw: dict[str, Any], *, node_id: int | None, vertical: Vertical
    ) -> NodeView:
        categories: list[Category] = []
        filters: list[Filter] = []
        for group in raw.get("navigatorGroups", []):
            for nav in group.get("navigatorList", []):
                if nav.get("id") == vertical.category_nav:
                    categories.extend(_parse_categories(nav))
                else:
                    filters.append(_parse_filter(nav))
        return cls(
            node_id=node_id,
            vertical=vertical,
            rows_found=raw.get("rowsFound", 0),
            breadcrumbs=tuple(_parse_breadcrumbs(raw.get("breadcrumbs", []))),
            categories=tuple(categories),
            filters=tuple(filters),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_navigation.py::TestParseMarketplace tests/test_navigation.py::TestParseFilterValueParams -v`
Expected: PASS. Pre-existing tests calling `from_api(..., node_id=...)` without `vertical` will fail — fix them in Step 5.

- [ ] **Step 5: Update existing `from_api` call sites in `tests/test_navigation.py`**

Add `vertical=MARKETPLACE` to every `NodeView.from_api(...)` call in the file (e.g. `TestParseRoot`, `TestParseApple`). For root, use `node_id=None, vertical=MARKETPLACE`.

Run: `uv run pytest tests/test_navigation.py -v`
Expected: PASS for all parser tests (navigate()/order tests come in later tasks; if any reference unbuilt symbols, leave them commented with a `# Task N` note).

- [ ] **Step 6: Commit**

```bash
git add src/willhaben/navigation.py tests/test_navigation.py
git commit -m "feat: vertical-aware category/filter parsing with NOT_SELECTABLE support"
```

---

## Task 4: `Order` model and the rewritten `navigate()`

**Files:**
- Modify: `src/willhaben/navigation.py`
- Test: `tests/test_navigation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_navigation.py
from willhaben.navigation import Order, navigate
from willhaben.verticals import AUTO


class TestNavigateRequest:
    def test_marketplace_node_query_param(self) -> None:
        stub = StubClient([load("navigate_apple.json")])
        view = navigate(2724, client=stub)
        assert stub.paths == ["atz/seo/kaufen-und-verkaufen/marktplatz"]
        assert stub.calls[0]["ATTRIBUTE_TREE"] == 2724
        assert stub.calls[0]["rows"] == 1
        assert view.vertical is MARKETPLACE

    def test_realestate_root_path_no_node(self) -> None:
        stub = StubClient([load("navigate_apple.json")])  # any nav payload; we assert routing
        navigate(vertical=REALESTATE, client=stub)
        assert stub.paths == ["atz/seo/immobilien/immobilien"]

    def test_selections_are_forwarded(self) -> None:
        stub = StubClient([load("navigate_apple.json")])
        navigate(vertical=AUTO, selections={"CAR_MODEL/MAKE": 1005}, client=stub)
        assert stub.calls[0]["CAR_MODEL/MAKE"] == 1005


class TestOrder:
    def test_order_holds_vertical_node_params(self) -> None:
        order = Order(MARKETPLACE, 2724, {"PRICE_TO": 900})
        assert order.vertical is MARKETPLACE
        assert order.node == 2724
        assert order.params == {"PRICE_TO": 900}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_navigation.py::TestNavigateRequest tests/test_navigation.py::TestOrder -v`
Expected: FAIL — `cannot import name 'Order'` / `navigate()` signature mismatch.

- [ ] **Step 3: Edit `src/willhaben/navigation.py`**

Add the `Order` dataclass (after `NodeView`) and rewrite `navigate`:

```python
from collections.abc import Mapping
from .client import QueryParams, QueryValue, WillhabenClient


@dataclass(frozen=True, slots=True)
class Order:
    """A persistable, replayable search agent: vertical + node + flat params."""

    vertical: Vertical
    node: int | None
    params: Mapping[str, QueryValue]


def navigate(
    node: int | None = None,
    *,
    vertical: Vertical = MARKETPLACE,
    selections: QueryParams | None = None,
    client: WillhabenClient | None = None,
) -> NodeView:
    """Fetch a catalog node and return its child categories and valid filters.

    `node` is the vertical's category id (or `None` for the vertical root).
    `selections` is a flat param dict forwarded so the response reflects
    dependent filters (e.g. pass a chosen make to populate auto `model`).
    """
    client = client or WillhabenClient()
    path, node_params = _target(vertical, node)
    params: dict[str, QueryValue] = {"rows": 1, **node_params}
    if selections:
        params.update(selections)
    return NodeView.from_api(client.search(path, params), node_id=node, vertical=vertical)
```

Delete the old `MARKETPLACE_PATH` import line in this file if present.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_navigation.py::TestNavigateRequest tests/test_navigation.py::TestOrder -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/willhaben/navigation.py tests/test_navigation.py
git commit -m "feat: Order model and vertical-aware navigate()"
```

---

## Task 5: Selection resolution — `NodeView.order(select, extra)`

**Files:**
- Modify: `src/willhaben/navigation.py`
- Test: `tests/test_navigation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_navigation.py
class TestNodeViewOrder:
    def _iphone(self) -> NodeView:
        return NodeView.from_api(
            load("navigate_iphone.json"), node_id=5015997, vertical=MARKETPLACE
        )

    def test_discrete_multi_select_stacks(self) -> None:
        view = self._iphone()
        order = view.order(select={"Speicherkapazität": ["256 GB", "512 GB"]})
        assert order.node == 5015997
        # both picks land on the same param as a list
        vals = order.params["treeAttributes"]
        assert isinstance(vals, list) and len(vals) == 2

    def test_free_form_range_tuple(self) -> None:
        view = self._iphone()
        order = view.order(select={"price": (100, 900)})
        assert order.params == {"PRICE_FROM": 100, "PRICE_TO": 900}

    def test_open_ended_range_skips_none(self) -> None:
        view = self._iphone()
        order = view.order(select={"price": (None, 900)})
        assert order.params == {"PRICE_TO": 900}

    def test_extra_raw_params_passthrough(self) -> None:
        view = self._iphone()
        order = view.order(extra={"areaId": 900})
        assert order.params == {"areaId": 900}

    def test_unknown_filter_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown filter"):
            self._iphone().order(select={"Nope": ["x"]})

    def test_unknown_value_raises(self) -> None:
        with pytest.raises(ValueError, match="no value"):
            self._iphone().order(select={"Speicherkapazität": ["999 GB"]})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_navigation.py::TestNodeViewOrder -v`
Expected: FAIL — `'NodeView' object has no attribute 'order'`.

- [ ] **Step 3: Edit `src/willhaben/navigation.py`**

Add a module-level resolver and `order()`/lookup methods on `NodeView`.

```python
def _merge(into: dict[str, QueryValue], params: Mapping[str, str]) -> None:
    for key, val in params.items():
        if key in into:
            existing = into[key]
            into[key] = [*existing, val] if isinstance(existing, list) else [existing, val]
        else:
            into[key] = val


def _resolve(f: Filter, value: Any) -> dict[str, QueryValue]:
    if f.type is FilterType.TEXT:
        if not isinstance(value, str):
            raise ValueError(f"filter {f.id!r} is TEXT; expected a string")
        return {f.params[0]: value}
    if f.type is FilterType.RANGE and isinstance(value, tuple):
        lo, hi = value
        out: dict[str, QueryValue] = {}
        if lo is not None:
            out[f.params[0]] = lo
        if hi is not None:
            out[f.params[1]] = hi
        return out
    # SELECT / HIERARCHICAL, or a RANGE selected by preset bucket label
    labels = [value] if isinstance(value, str) else list(value)
    if f.selection is SelectionMode.SINGLE and len(labels) > 1:
        raise ValueError(f"filter {f.id!r} is single-select; got {labels}")
    by_label = {v.label: v for v in f.values}
    by_value = {v.value: v for v in f.values}
    out = {}
    for label in labels:
        fv = by_label.get(label) or by_value.get(str(label))
        if fv is None:
            raise ValueError(f"filter {f.id!r} has no value {label!r}")
        _merge(out, fv.params)
    return out
```

Add methods to `NodeView` (inside the dataclass body, after `from_api`). `_resolve` already stacks multi-select values into a list, and different filters write distinct param keys, so `order()` just merges each filter's resolved params:

```python
    def _filter(self, key: str) -> Filter:
        for f in self.filters:
            if f.id == key or f.label == key:
                if not f.available:
                    raise ValueError(f"filter {key!r} is locked; select its prerequisite first")
                return f
        raise ValueError(f"unknown filter {key!r}")

    def order(
        self,
        select: Mapping[str, Any] | None = None,
        extra: Mapping[str, QueryValue] | None = None,
    ) -> Order:
        params: dict[str, QueryValue] = {}
        for key, value in (select or {}).items():
            params.update(_resolve(self._filter(key), value))
        if extra:
            params.update(extra)
        return Order(self.vertical, self.node_id, params)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_navigation.py::TestNodeViewOrder -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/willhaben/navigation.py tests/test_navigation.py
git commit -m "feat: NodeView.order resolves selections into an Order"
```

---

## Task 6: Generic `Ad` parsing, `SearchResult.node`, `counts_by_state`

**Files:**
- Modify: `src/willhaben/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from willhaben.models import Ad, SearchResult
from willhaben.navigation import NodeView


class TestAdPriceAliases:
    def test_price_amount_key(self) -> None:
        raw = {"id": 1, "description": "x",
               "attributes": {"attribute": [{"name": "PRICE/AMOUNT", "values": ["120.00"]}]}}
        assert Ad.from_api(raw).price is not None

    def test_plain_price_key(self) -> None:
        raw = {"id": 2, "description": "y",
               "attributes": {"attribute": [{"name": "PRICE", "values": ["300000"]}]}}
        assert Ad.from_api(raw).price is not None


class TestSearchResultNode:
    def test_node_parsed_from_same_payload(self, load_fixture) -> None:
        from willhaben.verticals import MARKETPLACE
        result = SearchResult.from_api(load_fixture("navigate_apple.json"), vertical=MARKETPLACE)
        assert isinstance(result.node, NodeView)
        assert any(c.label == "iPhone 17 Pro" for c in result.node.categories)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py::TestAdPriceAliases tests/test_models.py::TestSearchResultNode -v`
Expected: FAIL — plain `PRICE` returns `None`; `SearchResult.from_api()` has no `vertical` param / no `.node`.

- [ ] **Step 3: Edit `src/willhaben/models.py`**

In `Ad.from_api`, make price tolerant of both keys (replace the `price=` line):

```python
            price=_parse_price(_first(attrs.get("PRICE/AMOUNT")) or _first(attrs.get("PRICE"))),
```

Replace `_state_counts_from_raw` and the `SearchResult` class:

```python
from .verticals import MARKETPLACE, Vertical


@dataclass(frozen=True, slots=True)
class SearchResult:
    rows_found: int
    rows_returned: int
    page: int
    ads: list[Ad]
    raw: dict[str, Any] = field(repr=False, default_factory=dict)
    vertical: Vertical = MARKETPLACE

    @property
    def node(self) -> "NodeView":
        # node_id is informational here; the facets/categories come from `raw`.
        from .navigation import NodeView
        return NodeView.from_api(self.raw, node_id=None, vertical=self.vertical)

    @property
    def counts_by_state(self) -> dict[int, int]:
        """Map Bundesland areaId → ad count, derived from the location filter."""
        counts: dict[int, int] = {}
        for f in self.node.filters:
            if "areaId" not in f.params:
                continue
            for v in f.values:
                area = v.params.get("areaId")
                if area is not None and v.hits is not None:
                    counts[int(area)] = v.hits
        return counts

    @classmethod
    def from_api(cls, raw: dict[str, Any], *, vertical: Vertical = MARKETPLACE) -> "SearchResult":
        ad_list = raw.get("advertSummaryList", {}).get("advertSummary", [])
        return cls(
            rows_found=raw.get("rowsFound", 0),
            rows_returned=raw.get("rowsReturned", 0),
            page=raw.get("pageRequested", 1),
            ads=[Ad.from_api(a) for a in ad_list],
            raw=raw,
            vertical=vertical,
        )
```

Delete the old `_state_counts_from_raw` function entirely.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS. (If an existing `counts_by_state` test used the old `search_response.json`, verify it still maps state→count via the new derivation; adjust the expected dict to match the fixture's `state` navigator hits.)

- [ ] **Step 5: Commit**

```bash
git add src/willhaben/models.py tests/test_models.py
git commit -m "feat: generic Ad price aliases, SearchResult.node, derived counts_by_state"
```

---

## Task 7: `search`/`count`/`iter_ads` take an `Order`; `NodeView.search/count`

**Files:**
- Rewrite: `src/willhaben/search.py`
- Modify: `src/willhaben/navigation.py`
- Test: `tests/test_search.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search.py
from typing import Any

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


def _payload(rows_found: int = 0, ads: int = 0) -> dict[str, Any]:
    return {
        "rowsFound": rows_found,
        "advertSummaryList": {"advertSummary": [{"id": i, "description": "x",
            "attributes": {"attribute": []}} for i in range(ads)]},
    }


class TestSearchExecutesOrder:
    def test_marketplace_order_routes_with_params(self) -> None:
        stub = StubClient([_payload(rows_found=5, ads=5)])
        order = Order(MARKETPLACE, 2724, {"PRICE_TO": 900})
        result = search(order, client=stub)
        assert stub.paths == ["atz/seo/kaufen-und-verkaufen/marktplatz"]
        assert stub.calls[0]["ATTRIBUTE_TREE"] == 2724
        assert stub.calls[0]["PRICE_TO"] == 900
        assert result.rows_found == 5

    def test_realestate_order_uses_path_node(self) -> None:
        stub = StubClient([_payload()])
        count(Order(REALESTATE, 102, {}), client=stub)
        assert stub.paths == ["atz/2/102"]

    def test_sort_only_on_search(self) -> None:
        stub = StubClient([_payload(ads=1)])
        from willhaben.constants import SortOrder
        search(Order(MARKETPLACE, None, {}), sort=SortOrder.PRICE_ASC, client=stub)
        assert stub.calls[0]["sort"] == int(SortOrder.PRICE_ASC)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_search.py::TestSearchExecutesOrder -v`
Expected: FAIL — `search()` still uses domain kwargs.

- [ ] **Step 3: Rewrite `src/willhaben/search.py`**

```python
from __future__ import annotations

from collections.abc import Iterator

from .client import QueryValue, WillhabenClient
from .constants import MAX_ROWS_PER_PAGE, SortOrder
from .models import Ad, SearchResult
from .navigation import Order
from .verticals import _target


def _execute(
    order: Order, *, rows: int, page: int, sort: SortOrder | int | None,
    client: WillhabenClient,
) -> SearchResult:
    path, node_params = _target(order.vertical, order.node)
    params: dict[str, QueryValue] = {"rows": rows, "page": page, **node_params}
    params.update(order.params)
    if sort is not None:
        params["sort"] = int(sort)
    return SearchResult.from_api(client.search(path, params), vertical=order.vertical)


def search(
    order: Order, *, rows: int = 30, page: int = 1,
    sort: SortOrder | int | None = None, client: WillhabenClient | None = None,
) -> SearchResult:
    """Run a single search for an Order. `rows` is server-capped at 200."""
    client = client or WillhabenClient()
    return _execute(order, rows=rows, page=page, sort=sort, client=client)


def count(order: Order, *, client: WillhabenClient | None = None) -> int:
    """Return only the total result count for an Order via a `rows=1` request."""
    client = client or WillhabenClient()
    return _execute(order, rows=1, page=1, sort=None, client=client).rows_found


def iter_ads(
    order: Order, *, max_results: int | None = None,
    sort: SortOrder | int | None = None, client: WillhabenClient | None = None,
) -> Iterator[Ad]:
    """Yield ads for an Order across all pages, stopping at `max_results`."""
    client = client or WillhabenClient()
    yielded = 0
    page = 1
    while True:
        result = _execute(order, rows=MAX_ROWS_PER_PAGE, page=page, sort=sort, client=client)
        if not result.ads:
            return
        for ad in result.ads:
            yield ad
            yielded += 1
            if max_results is not None and yielded >= max_results:
                return
        if yielded >= result.rows_found:
            return
        page += 1
```

- [ ] **Step 4: Add `NodeView.search`/`NodeView.count` conveniences in `src/willhaben/navigation.py`**

```python
    def search(self, *, select=None, extra=None, rows=30, page=1, sort=None, client=None):
        from .search import search as _search
        return _search(self.order(select, extra), rows=rows, page=page, sort=sort, client=client)

    def count(self, *, select=None, extra=None, client=None) -> int:
        from .search import count as _count
        return _count(self.order(select, extra), client=client)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_search.py::TestSearchExecutesOrder -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Delete the obsolete domain-kwarg search tests**

Remove any test in `tests/test_search.py` that calls `search(keyword=...)` / `category_id=` / `category=` kwargs. Those signatures no longer exist.

Run: `uv run pytest tests/test_search.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/willhaben/search.py src/willhaben/navigation.py tests/test_search.py
git commit -m "feat: Order-based search/count/iter_ads and NodeView conveniences"
```

---

## Task 8: Remove `realestate.py` and update package exports

**Files:**
- Delete: `src/willhaben/realestate.py`, `tests/test_realestate_search.py`, `tests/test_realestate_models.py`
- Modify: `src/willhaben/__init__.py`
- Test: `tests/test_exports.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_exports.py
import willhaben


def test_new_public_surface() -> None:
    for name in ["navigate", "Order", "Vertical", "MARKETPLACE", "REALESTATE", "AUTO",
                 "search", "count", "iter_ads", "NodeView", "Filter", "FilterValue",
                 "Category", "Ad", "SearchResult", "SortOrder", "WillhabenClient"]:
        assert hasattr(willhaben, name), name


def test_removed_symbols_gone() -> None:
    for name in ["search_realestate", "RealEstateAd", "RealEstateCategory",
                 "EstateMiscCategory", "OfferType", "RealEstateSearchResult"]:
        assert not hasattr(willhaben, name), name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_exports.py -v`
Expected: FAIL — removed symbols still exported; `Vertical`/`Order` not yet exported.

- [ ] **Step 3: Delete files and rewrite `src/willhaben/__init__.py`**

```bash
git rm src/willhaben/realestate.py tests/test_realestate_search.py tests/test_realestate_models.py
```

```python
# src/willhaben/__init__.py
from __future__ import annotations

from .client import WillhabenAPIError, WillhabenClient
from .constants import AREAS, AREAS_BY_ID, MAX_ROWS_PER_PAGE, Area, SortOrder
from .models import Ad, SearchResult
from .navigation import (
    Category,
    Crumb,
    Filter,
    FilterType,
    FilterValue,
    NodeView,
    Order,
    SelectionMode,
    navigate,
)
from .search import count, iter_ads, search
from .verticals import AUTO, MARKETPLACE, REALESTATE, Vertical

__all__ = [
    "AREAS", "AREAS_BY_ID", "AUTO", "Ad", "Area", "Category", "Crumb", "Filter",
    "FilterType", "FilterValue", "MARKETPLACE", "MAX_ROWS_PER_PAGE", "NodeView",
    "Order", "REALESTATE", "SearchResult", "SelectionMode", "SortOrder", "Vertical",
    "WillhabenAPIError", "WillhabenClient", "count", "iter_ads", "navigate", "search",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_exports.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Remove the stale `MARKETPLACE_PATH` constant**

If nothing imports `MARKETPLACE_PATH` anymore (`grep -rn MARKETPLACE_PATH src tests`), delete its definition from `src/willhaben/constants.py`.

Run: `uv run pytest -q`
Expected: PASS (non-live suite green).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor!: remove realestate module; export Vertical/Order; drop MARKETPLACE_PATH"
```

---

## Task 9: Capture realestate/auto fixtures and add their parser tests

**Files:**
- Create: `tests/fixtures/navigate_realestate_root.json`, `navigate_realestate_other.json`, `navigate_auto.json`, `navigate_auto_bmw.json`
- Modify: `tests/test_navigation.py`

- [ ] **Step 1: Capture the fixtures from live willhaben**

Run this once (hits the network; ~4 polite requests):

```bash
uv run python - <<'PY'
import json
from pathlib import Path
from willhaben.client import WillhabenClient
c = WillhabenClient()
F = Path("tests/fixtures")
targets = {
    "navigate_realestate_root.json": ("atz/seo/immobilien/immobilien", {}),
    "navigate_realestate_other.json": ("atz/2/35", {}),
    "navigate_auto.json": ("atz/seo/gebrauchtwagen/auto", {}),
    "navigate_auto_bmw.json": ("atz/seo/gebrauchtwagen/auto", {"CAR_MODEL/MAKE": 1005}),
}
for name, (path, extra) in targets.items():
    raw = c.search(path, {"rows": 1, **extra})
    (F / name).write_text(json.dumps(raw, ensure_ascii=False, indent=1))
    print("wrote", name, raw.get("rowsFound"))
PY
```

Expected: prints four lines with non-zero `rowsFound`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_navigation.py
from willhaben.verticals import AUTO, REALESTATE


class TestParseRealestate:
    def test_categories_from_search_id(self) -> None:
        view = NodeView.from_api(
            load("navigate_realestate_root.json"), node_id=None, vertical=REALESTATE
        )
        labels = {c.label for c in view.categories}
        assert "Haus kaufen" in labels
        by_label = {c.label: c.id for c in view.categories}
        assert by_label["Haus kaufen"] == 102

    def test_other_node_has_objecttype_filter(self) -> None:
        view = NodeView.from_api(
            load("navigate_realestate_other.json"), node_id=35, vertical=REALESTATE
        )
        assert view.categories == ()
        assert any(f.id == "ownagetype" for f in view.filters)


class TestParseAuto:
    def test_model_locked_until_make(self) -> None:
        view = NodeView.from_api(load("navigate_auto.json"), node_id=None, vertical=AUTO)
        model = next(f for f in view.filters if f.id == "model")
        assert model.available is False
        assert model.values == ()

    def test_model_unlocked_with_make(self) -> None:
        view = NodeView.from_api(load("navigate_auto_bmw.json"), node_id=None, vertical=AUTO)
        model = next(f for f in view.filters if f.id == "model")
        assert model.available is True
        assert len(model.values) > 0
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_navigation.py::TestParseRealestate tests/test_navigation.py::TestParseAuto -v`
Expected: PASS (4 passed). If `model.available` is True at the locked stage, re-check Task 3's `available=nav_type != "NOT_SELECTABLE"`.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/navigate_realestate_root.json tests/fixtures/navigate_realestate_other.json tests/fixtures/navigate_auto.json tests/fixtures/navigate_auto_bmw.json tests/test_navigation.py
git commit -m "test: realestate/auto navigation fixtures and parser guards"
```

---

## Task 10: Live drift guards and version bump

**Files:**
- Modify: `tests/test_live.py`, `pyproject.toml`

- [ ] **Step 1: Rewrite the live tests for the new API**

Replace marketplace/realestate live tests that used old signatures. Add:

```python
# tests/test_live.py
import pytest

from willhaben import AUTO, MARKETPLACE, REALESTATE, count, navigate

pytestmark = pytest.mark.live


def test_realestate_search_id_scopes_via_path() -> None:
    view = navigate(vertical=REALESTATE)
    by_label = {c.label: c.id for c in view.categories}
    assert by_label.get("Haus kaufen") == 102
    scoped = count(navigate(102, vertical=REALESTATE).order())
    root = count(navigate(vertical=REALESTATE).order())
    assert scoped < root


def test_search_id_as_param_does_not_scope() -> None:
    # the categoryId-class trap: searchId as a query param must be ignored
    root = navigate(vertical=REALESTATE)
    assert count(root.order(extra={"searchId": 102})) == root.rows_found


def test_auto_model_unlocks_after_make() -> None:
    locked = next(f for f in navigate(vertical=AUTO).filters if f.id == "model")
    assert locked.available is False
    unlocked = next(
        f for f in navigate(vertical=AUTO, selections={"CAR_MODEL/MAKE": 1005}).filters
        if f.id == "model"
    )
    assert unlocked.available is True


def test_marketplace_category_filter_reduces_count() -> None:
    apple = navigate(2724, vertical=MARKETPLACE)
    storage = next(f for f in apple.filters if f.id == "Speicherkapazität")
    filtered = count(apple.order(select={storage.label: [storage.values[0].label]}))
    assert filtered < apple.rows_found
```

- [ ] **Step 2: Run the live tests**

Run: `uv run pytest -m live tests/test_live.py -v`
Expected: PASS (4 passed). These make real requests; allow a few seconds each (polite delay).

- [ ] **Step 3: Bump the version**

In `pyproject.toml` change `version = "0.4.0"` to `version = "0.5.0"`.

- [ ] **Step 4: Run the full non-live suite**

Run: `uv run pytest -q`
Expected: all pass, no errors, no skips other than `-m live`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_live.py pyproject.toml
git commit -m "test: live guards for vertical navigation; bump to 0.5.0"
```

---

## Notes for the implementer

- **Run order matters within Tasks 2–5:** the navigation parser is rewritten incrementally; some `test_navigation.py` tests stay red between tasks. That is expected — each task's own tests must pass, and the whole file must be green by the end of Task 5.
- **`uv run` prefix** is required for all python/pytest invocations in this repo.
- **Live tests** (`-m live`) hit willhaben; never put them in the default run. Counts drift, so live assertions are always relative (`scoped < root`), never exact equality.
- **No silent param drops:** if `order()` ever produces an empty `params` from a non-empty `select`, that is a bug — every selection must map to at least one param.
