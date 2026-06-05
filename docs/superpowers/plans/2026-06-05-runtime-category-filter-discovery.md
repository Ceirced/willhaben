# Runtime Category & Filter Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runtime `navigate()` primitive to the `willhaben` package that fetches a marketplace category's subcategories and filters on demand, so nothing has to be predefined — plus the client fix that makes multi-select facets work and a fix for the silently-broken category parameter.

**Architecture:** willhaben's marketplace search response (`isNavigation=true`) already returns a self-describing `navigatorGroups` block containing both the node's child categories and its filters. `navigate(node)` does one request and parses that block into frozen dataclasses. Category scoping uses the `ATTRIBUTE_TREE` URL param (verified working) instead of the existing `categoryId` (verified ignored). Multi-select facets need the client to emit repeated query params.

**Tech Stack:** Python 3.13, httpx (HTTP/2), pytest, uv, ruff, ty. All new public types are `@dataclass(frozen=True, slots=True)`; all functions are module-level, matching the existing `search.py`/`realestate.py` style.

**Reference spec:** `docs/superpowers/specs/2026-06-05-runtime-category-filter-discovery-design.md`

**Run tests with:** `uv run pytest` (live tests are excluded by default via `addopts = "-m 'not live'"`).

---

### Task 1: Client — repeated query params for multi-select facets

The client currently coerces every param value to `str`, so a list value becomes the string `"[1, 2]"`. Make list/tuple values pass through as a list of strings (httpx expands those to repeated query keys, e.g. `treeAttributes=2537&treeAttributes=2540`).

**Files:**
- Modify: `src/willhaben/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing test**

Add this method to the existing `TestRequestSuccess` class in `tests/test_client.py`:

```python
    def test_list_param_expands_to_repeated_values(
        self, client: WillhabenClient
    ) -> None:
        client._http.get.return_value = make_response({})
        client.search(MARKETPLACE_PATH, {"treeAttributes": [2537, 2540]})
        params = client._http.get.call_args.kwargs["params"]
        assert params["treeAttributes"] == ["2537", "2540"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py::TestRequestSuccess::test_list_param_expands_to_repeated_values -v`
Expected: FAIL — the current code produces `"[2537, 2540]"` (a string), not `["2537", "2540"]`.

- [ ] **Step 3: Implement the change**

In `src/willhaben/client.py`, add `Mapping` to the imports (top of file, after `from typing import Any`):

```python
from collections.abc import Mapping
```

Replace the `search` method signature and the query-building line. Current:

```python
    def search(
        self, path: str, params: dict[str, str | int]
    ) -> dict[str, Any]:
        query = {k: str(v) for k, v in params.items() if v is not None}
        query.setdefault("isNavigation", "true")
        url = f"{API_ROOT}/{path}"
```

becomes:

```python
    def search(
        self, path: str, params: Mapping[str, str | int | list[int]]
    ) -> dict[str, Any]:
        query: dict[str, str | list[str]] = {}
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                query[key] = [str(v) for v in value]
            else:
                query[key] = str(value)
        query.setdefault("isNavigation", "true")
        url = f"{API_ROOT}/{path}"
```

(`str` is itself a `Sequence`, so the `isinstance` check deliberately tests `(list, tuple)` only — a string value still takes the scalar branch.)

- [ ] **Step 4: Run the full client suite to verify pass + no regressions**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS — the new test plus all existing `TestRequestSuccess`/`TestRetryBehavior`/`TestPathArgument` tests (they read `params["isNavigation"]` etc., which still works because `query` is still a dict).

- [ ] **Step 5: Commit**

```bash
git add src/willhaben/client.py tests/test_client.py
git commit -m "feat: support list-valued query params (repeated keys)"
```

---

### Task 2: Replace the broken `category_id` with a working `category`

`category_id` maps to `categoryId`, which the marketplace endpoint ignores for every value. Replace it with `category`, mapping to `ATTRIBUTE_TREE`. Also broaden the param/extra types so list-valued facets can flow through `extra_params`.

**Files:**
- Modify: `src/willhaben/search.py`
- Test: `tests/test_search.py`

- [ ] **Step 1: Update the tests first (rename + new mapping)**

In `tests/test_search.py`, replace every `category_id=None` with `category=None` and every `category_id=42` with `category=42`. There are occurrences in `test_minimal`, `test_all_options`, `test_is_private_false_omitted`, `test_sort_int`, and `test_extra_overrides`.

Then in `test_all_options`, change the asserted dict entry `"categoryId": 42,` to `"ATTRIBUTE_TREE": 42,`.

Add a focused test to the `TestBuildParams` class:

```python
    def test_category_maps_to_attribute_tree(self) -> None:
        params = _build_params(
            keyword=None,
            price_from=None,
            price_to=None,
            area_id=None,
            category=2691,
            is_private=None,
            sort=None,
            rows=1,
            page=1,
            extra=None,
        )
        assert params["ATTRIBUTE_TREE"] == 2691
        assert "categoryId" not in params
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_search.py -v`
Expected: FAIL — `_build_params` has no `category` keyword argument yet (TypeError), and the `ATTRIBUTE_TREE` assertion fails.

- [ ] **Step 3: Implement the rename in `src/willhaben/search.py`**

Add `Mapping` to imports (after `from collections.abc import Iterator`):

```python
from collections.abc import Iterator, Mapping
```

In `_build_params`, change the parameter `category_id: int | None,` to `category: int | None,`, change the params dict annotation, and replace the mapping block. Current:

```python
    extra: dict[str, str | int] | None,
) -> dict[str, str | int]:
    params: dict[str, str | int] = {"rows": rows, "page": page}
```

becomes:

```python
    extra: Mapping[str, str | int | list[int]] | None,
) -> dict[str, str | int | list[int]]:
    params: dict[str, str | int | list[int]] = {"rows": rows, "page": page}
```

and current:

```python
    if category_id is not None:
        params["categoryId"] = category_id
```

becomes:

```python
    if category is not None:
        params["ATTRIBUTE_TREE"] = category
```

In `search`, `count`, and `iter_ads`: change each `category_id: int | None = None,` parameter to `category: int | None = None,`, change each `category_id=category_id,` call-through to `category=category,`, and change each `extra_params: dict[str, str | int] | None = None,` to `extra_params: Mapping[str, str | int | list[int]] | None = None,`.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_search.py -v`
Expected: PASS — all `TestBuildParams`/`TestSearch`/`TestCount`/`TestIterAds` tests.

- [ ] **Step 5: Type-check and commit**

Run: `uv run ty check src/willhaben/search.py src/willhaben/client.py`
Expected: no errors.

```bash
git add src/willhaben/search.py tests/test_search.py
git commit -m "fix: scope marketplace categories via ATTRIBUTE_TREE, not ignored categoryId"
```

---

### Task 3: Capture navigation fixtures from the live API

Capture three trimmed real responses for deterministic offline parser tests. This is a one-time data-gathering step; the command hits the live API.

**Files:**
- Create: `tests/fixtures/navigate_root.json`
- Create: `tests/fixtures/navigate_apple.json`
- Create: `tests/fixtures/navigate_iphone.json`

- [ ] **Step 1: Run the capture command**

```bash
uv run python - <<'PY'
import json
from pathlib import Path
from willhaben.client import WillhabenClient
from willhaben.constants import MARKETPLACE_PATH

client = WillhabenClient()
out = Path("tests/fixtures")
KEEP = ("rowsFound", "breadcrumbs", "navigatorGroups")

def grab(node, name):
    params = {"rows": 1}
    if node is not None:
        params["ATTRIBUTE_TREE"] = node
    raw = client.search(MARKETPLACE_PATH, params)
    trimmed = {k: raw[k] for k in KEEP if k in raw}
    (out / name).write_text(json.dumps(trimmed, ensure_ascii=False, indent=1))
    n_cat = sum(
        len(g2.get("possibleValues", []))
        for g in trimmed.get("navigatorGroups", [])
        for nav in g.get("navigatorList", [])
        if nav.get("id") == "category"
        for g2 in (nav.get("groupedPossibleValues") or [{"possibleValues": nav.get("possibleValues", [])}])
    )
    print(f"{name}: rowsFound={trimmed.get('rowsFound')} categories={n_cat}")

grab(None, "navigate_root.json")
grab(2724, "navigate_apple.json")
grab(5015997, "navigate_iphone.json")
PY
```

Expected output (counts approximate, will drift over time):
```
navigate_root.json: rowsFound=13201709 categories=19
navigate_apple.json: rowsFound=13907 categories=45
navigate_iphone.json: rowsFound=258 categories=0
```

- [ ] **Step 2: Sanity-check the fixtures**

Run:
```bash
uv run python -c "
import json
for n in ('navigate_root','navigate_apple','navigate_iphone'):
    d = json.load(open(f'tests/fixtures/{n}.json'))
    assert d['navigatorGroups'], n
    assert 'breadcrumbs' in d, n
print('fixtures OK')
"
```
Expected: `fixtures OK`

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/navigate_root.json tests/fixtures/navigate_apple.json tests/fixtures/navigate_iphone.json
git commit -m "test: capture marketplace navigation fixtures"
```

---

### Task 4: Navigation data model + response parser

Create the module with the frozen dataclasses and `NodeView.from_api`, tested against the fixtures.

**Files:**
- Create: `src/willhaben/navigation.py`
- Test: `tests/test_navigation.py`

- [ ] **Step 1: Write the failing parser tests**

Create `tests/test_navigation.py`:

```python
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


class TestEmptyResponse:
    def test_missing_navigator_groups_yields_empty_tuples(self) -> None:
        view = NodeView.from_api({"rowsFound": 0}, node_id=None)
        assert view.categories == ()
        assert view.filters == ()
        assert view.breadcrumbs == ()
        assert view.rows_found == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_navigation.py -v`
Expected: FAIL — `willhaben.navigation` does not exist (ImportError).

- [ ] **Step 3: Create `src/willhaben/navigation.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .client import WillhabenClient
from .constants import MARKETPLACE_PATH

_TRAILING_ID = re.compile(r"-(\d+)$")

_NAVIGATOR_TYPES = {
    "TEXT_SEARCH": "TEXT",
    "STANDARD": "SELECT",
    "RANGE": "RANGE",
    "HIERARCHICAL": "HIERARCHICAL",
}


class FilterType(StrEnum):
    RANGE = "RANGE"
    SELECT = "SELECT"
    HIERARCHICAL = "HIERARCHICAL"
    TEXT = "TEXT"


class SelectionMode(StrEnum):
    SINGLE = "SINGLE"
    MULTI = "MULTI"


@dataclass(frozen=True, slots=True)
class FilterValue:
    label: str
    value: str          # the id to send in the URL param, e.g. "2537"
    hits: int | None


@dataclass(frozen=True, slots=True)
class Filter:
    id: str                       # navigator id, e.g. "Speicherkapazität"
    label: str
    params: tuple[str, ...]       # ("treeAttributes",) or ("PRICE_FROM", "PRICE_TO")
    type: FilterType
    selection: SelectionMode
    values: tuple[FilterValue, ...]


@dataclass(frozen=True, slots=True)
class Category:
    id: int             # ATTRIBUTE_TREE id, e.g. 5015997
    label: str
    hits: int | None


@dataclass(frozen=True, slots=True)
class Crumb:
    label: str
    node_id: int | None


def _iter_values(nav: dict[str, Any]) -> list[dict[str, Any]]:
    values = list(nav.get("possibleValues") or [])
    for grouped in nav.get("groupedPossibleValues") or []:
        values.extend(grouped.get("possibleValues") or [])
    return values


def _url_value(value: dict[str, Any], param: str | None = None) -> str | None:
    for rep in value.get("urlParamRepresentationForValue") or []:
        if param is None or rep.get("urlParameterName") == param:
            raw = rep.get("value")
            if raw is not None:
                return str(raw)
    return None


def _parse_categories(nav: dict[str, Any]) -> list[Category]:
    out: list[Category] = []
    for value in _iter_values(nav):
        raw_id = _url_value(value, "ATTRIBUTE_TREE")
        if raw_id is None:
            continue
        out.append(
            Category(id=int(raw_id), label=value.get("label", ""), hits=value.get("hits"))
        )
    return out


def _parse_filter(nav: dict[str, Any]) -> Filter:
    params = tuple(
        p["urlParameterName"]
        for p in nav.get("urlConstructionInformation", {}).get("urlParams", [])
        if "urlParameterName" in p
    )
    values: list[FilterValue] = []
    for value in _iter_values(nav):
        raw = _url_value(value)
        if raw is None:
            continue
        values.append(
            FilterValue(label=value.get("label", ""), value=raw, hits=value.get("hits"))
        )
    return Filter(
        id=nav.get("id", ""),
        label=nav.get("label", ""),
        params=params,
        type=FilterType(_NAVIGATOR_TYPES.get(nav.get("navigatorType", ""), "SELECT")),
        selection=(
            SelectionMode.MULTI
            if nav.get("navigatorSelectionType") == "MULTI_SELECT"
            else SelectionMode.SINGLE
        ),
        values=tuple(values),
    )


def _parse_breadcrumbs(raw: list[dict[str, Any]]) -> list[Crumb]:
    crumbs: list[Crumb] = []
    for item in raw:
        segment = (item.get("seoUrl", "") or "").rstrip("/").rsplit("/", 1)[-1]
        match = _TRAILING_ID.search(segment)
        crumbs.append(
            Crumb(
                label=item.get("displayName", ""),
                node_id=int(match.group(1)) if match else None,
            )
        )
    return crumbs


@dataclass(frozen=True, slots=True)
class NodeView:
    node_id: int | None
    rows_found: int
    breadcrumbs: tuple[Crumb, ...]
    categories: tuple[Category, ...]   # children; () at a leaf
    filters: tuple[Filter, ...]        # every non-category navigator

    @classmethod
    def from_api(cls, raw: dict[str, Any], *, node_id: int | None) -> NodeView:
        categories: list[Category] = []
        filters: list[Filter] = []
        for group in raw.get("navigatorGroups", []):
            for nav in group.get("navigatorList", []):
                if nav.get("id") == "category":
                    categories.extend(_parse_categories(nav))
                else:
                    filters.append(_parse_filter(nav))
        return cls(
            node_id=node_id,
            rows_found=raw.get("rowsFound", 0),
            breadcrumbs=tuple(_parse_breadcrumbs(raw.get("breadcrumbs", []))),
            categories=tuple(categories),
            filters=tuple(filters),
        )


def navigate(
    node: int | None = None, *, client: WillhabenClient | None = None
) -> NodeView:
    """Fetch a marketplace catalog node and return its child categories and the
    filters valid there.

    `node` is an `ATTRIBUTE_TREE` category id (any depth — e.g. 2724 for Apple,
    5015997 for the iPhone 17 Pro leaf), or `None` for the marketplace root.
    Performs one live request. `categories` is empty at a leaf; `filters` holds
    every non-category navigator (price, condition, storage, …) with its URL
    parameter name, type, selection mode, and possible values.
    """
    client = client or WillhabenClient()
    params: dict[str, str | int | list[int]] = {"rows": 1}
    if node is not None:
        params["ATTRIBUTE_TREE"] = node
    return NodeView.from_api(client.search(MARKETPLACE_PATH, params), node_id=node)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_navigation.py -v`
Expected: PASS — all parser tests.

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff check src/willhaben/navigation.py && uv run ty check src/willhaben/navigation.py`
Expected: no errors.

```bash
git add src/willhaben/navigation.py tests/test_navigation.py
git commit -m "feat: add navigate() catalog discovery parser and data model"
```

---

### Task 5: `navigate()` request wiring test

`navigate()` already exists from Task 4; this task pins its request behaviour (correct path, `ATTRIBUTE_TREE` set/omitted) with a stub client.

**Files:**
- Test: `tests/test_navigation.py`

- [ ] **Step 1: Write the failing tests**

First extend the top-of-file imports in `tests/test_navigation.py` so everything stays at module top (ruff E402). Change the import block to:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from willhaben.constants import MARKETPLACE_PATH
from willhaben.navigation import FilterType, NodeView, SelectionMode, navigate
```

Then add the stub class (after the `load` helper):

```python
class StubClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def search(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.paths.append(path)
        self.calls.append(params)
        return self.responses.pop(0)
```

then the tests:

```python
class TestNavigate:
    def test_scopes_by_attribute_tree(self) -> None:
        client = StubClient([load("navigate_apple.json")])
        view = navigate(2724, client=client)  # ty: ignore[invalid-argument-type]
        assert client.paths[0] == MARKETPLACE_PATH
        assert client.calls[0]["ATTRIBUTE_TREE"] == 2724
        assert any(c.id == 5015997 for c in view.categories)

    def test_root_omits_attribute_tree(self) -> None:
        client = StubClient([load("navigate_root.json")])
        navigate(client=client)  # ty: ignore[invalid-argument-type]
        assert "ATTRIBUTE_TREE" not in client.calls[0]
```

- [ ] **Step 2: Run tests to verify pass**

Run: `uv run pytest tests/test_navigation.py::TestNavigate -v`
Expected: PASS (the `navigate` implementation from Task 4 already satisfies these).

- [ ] **Step 3: Commit**

```bash
git add tests/test_navigation.py
git commit -m "test: pin navigate() request wiring"
```

---

### Task 6: Public exports + version bump

**Files:**
- Modify: `src/willhaben/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_navigation.py`

- [ ] **Step 1: Write the failing export test**

Add to `tests/test_navigation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_navigation.py::TestPublicApi -v`
Expected: FAIL — `willhaben` has no attribute `navigate`.

- [ ] **Step 3: Add the exports**

In `src/willhaben/__init__.py`, add this import block (after the `from .models import ...` line):

```python
from .navigation import (
    Category,
    Crumb,
    Filter,
    FilterType,
    FilterValue,
    NodeView,
    SelectionMode,
    navigate,
)
```

Then add these names to the `__all__` list (keep it alphabetically grouped as the file already is):

```python
    "Category",
    "Crumb",
    "Filter",
    "FilterType",
    "FilterValue",
    "NodeView",
    "SelectionMode",
    "navigate",
```

- [ ] **Step 4: Bump the version**

In `pyproject.toml`, change `version = "0.3.0"` to `version = "0.4.0"`.

- [ ] **Step 5: Run test + full suite to verify pass**

Run: `uv run pytest`
Expected: PASS — entire offline suite (live tests excluded by default).

- [ ] **Step 6: Lint, type-check, commit**

Run: `uv run ruff check src tests && uv run ty check src`
Expected: no errors.

```bash
git add src/willhaben/__init__.py pyproject.toml tests/test_navigation.py
git commit -m "feat: export navigation API and bump to 0.4.0"
```

---

### Task 7: Live drift + category-effect guards

Two `@pytest.mark.live` tests (excluded from the default run): one detects category-tree drift like the existing area-drift test; one guards against the exact `categoryId` failure mode (a category param that doesn't actually reduce results).

**Files:**
- Modify: `tests/test_live.py`

- [ ] **Step 1: Add the live tests**

In `tests/test_live.py`, add `navigate` to the `from willhaben import (...)` block (keep alphabetical: it goes after `count_realestate`... place `navigate` appropriately, e.g. after `count_realestate,`):

```python
from willhaben import (
    AREAS,
    RealEstateCategory,
    count,
    count_realestate,
    navigate,
)
```

Then append:

```python
@pytest.mark.live
def test_live_navigate_root_lists_known_categories() -> None:
    """Drift check: the marketplace root must expose its top-level categories.

    If this fails, willhaben changed the top-level category labels/ids; inspect
    `navigate()` output and update expectations.
    """
    view = navigate()
    labels = {c.label for c in view.categories}
    assert "Smartphones / Telefonie" in labels
    assert len(view.categories) >= 15


@pytest.mark.live
def test_live_navigate_reaches_iphone_leaf() -> None:
    """Apple (2724) must list the iPhone 17 Pro leaf (5015997) as a child."""
    view = navigate(2724)
    assert any(c.id == 5015997 for c in view.categories)


@pytest.mark.live
def test_live_category_param_actually_filters() -> None:
    """Guard against the categoryId bug class: scoping to a category MUST reduce
    the result count. (categoryId was silently ignored and returned everything.)
    """
    assert count(category=2691) < count()
```

- [ ] **Step 2: Run the live tests explicitly to verify they pass**

Run: `uv run pytest tests/test_live.py -m live -v`
Expected: PASS (requires network). These are excluded from the default `uv run pytest` run.

- [ ] **Step 3: Confirm the default run still excludes live tests**

Run: `uv run pytest`
Expected: PASS, live tests deselected.

- [ ] **Step 4: Commit**

```bash
git add tests/test_live.py
git commit -m "test: live drift + category-effect guards for navigation"
```

---

## Self-review notes

- **Spec coverage:** module/exports (Tasks 4–6), data model (Task 4), `navigate()` + parsing rules incl. `SINGLE_SELECT→SINGLE` and grouped/flat values (Task 4), client repeated-params fix (Task 1), replace `category_id`→`category`/`ATTRIBUTE_TREE` (Task 2), fixtures root/apple/iphone-leaf (Task 3), unit + client + search + live tests incl. the category-effect guard (Tasks 1–2, 4–7), error handling for missing `navigatorGroups` (Task 4 `TestEmptyResponse`). Out-of-scope items (app wiring, other verticals, caching, `Navigator` wrapper) are intentionally absent.
- **Naming consistency:** `navigate`, `NodeView.from_api`, `Category.id`, `Filter.params/type/selection/values`, `FilterValue.value`, `Crumb.node_id`, `FilterType`, `SelectionMode` are used identically across module, tests, and exports.
- **Type note:** `client.search` and `search()` use `Mapping[...]` (covariant) at boundaries so existing `dict[str, str | int]` callers (e.g. `realestate.py`) remain assignable without edits.
