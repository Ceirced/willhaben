# Runtime category & filter discovery

**Date:** 2026-06-05
**Status:** Approved design, ready for implementation plan
**Scope:** the `willhaben` package only. The `willhaben-app` wiring (drill-down
UI, dynamic filter form, JSONB/validation changes) is a separate follow-up spec.

## Problem

Adding a new marketplace category or filter today means manually digging IDs and
`treeAttributes` out of the willhaben website and hand-writing `IntEnum` classes
(`RealEstateCategory`, `EstateMiscCategory`, …). The downstream consumer,
`willhaben-app`, wants to let users pick *any* subcategory and *any* filter to
track over time, without anything being predefined. We need to fetch
subcategories and filters on demand at runtime.

## Key finding: the API is self-describing

Every marketplace search response (with `isNavigation=true`, which the client
already sends) carries a `navigatorGroups` block describing **both** the child
categories and the filters valid at the current node. This was verified live:

- **Categories are walkable by id alone.** A `category` navigator
  (`navigatorType: HIERARCHICAL`, param `ATTRIBUTE_TREE`) lists child categories;
  each value carries its own numeric id. Passing `ATTRIBUTE_TREE=<id>` on the
  marketplace root path scopes the search to that node at *any* depth — no SEO
  slug or ancestor path needed. Confirmed: `ATTRIBUTE_TREE=2724` (Apple) → 13,907
  results, identical to walking `…/smartphones-handys/apple-2724`; and
  `ATTRIBUTE_TREE=5015997` lands directly on the "iPhone 17 Pro" leaf (258
  results).
- **Filters self-describe.** Each non-category navigator exposes its URL
  `parameterName`, type (`RANGE` / `STANDARD` / `HIERARCHICAL`), selection mode
  (`SINGLE_SELECT` / `MULTI_SELECT`), and possible values with numeric ids.
- **Facets stack via `treeAttributes`.** Multi-select facets (condition, storage,
  unlocked, …) all emit the `treeAttributes` param; values are globally unique
  numeric ids, so multiple selections become repeated
  `treeAttributes=X&treeAttributes=Y`. Confirmed: adding `treeAttributes=2537`
  drops the Apple count 13,907 → 9,933.

A tracked search therefore reduces to a **flat dict of willhaben URL params** —
exactly what `willhaben-app` already stores in its JSONB `filters` column and what
the package already forwards via `search(extra_params=…)`.

## The `categoryId` bug (replace it)

The existing `search(category_id=…)` maps to a `categoryId` URL param that the
marketplace endpoint **silently ignores for every value**:

| param | result count |
| --- | ---: |
| no filter (whole marktplatz) | 13,201,709 |
| `categoryId=2691` (valid top-level) | 13,201,709 |
| `categoryId=5015997` (valid leaf) | 13,201,709 |
| `categoryId=42` (the unit-test value) | 13,201,709 |
| `categoryId=99999999` (nonsense) | 13,201,709 |
| `ATTRIBUTE_TREE=2691` | **103,639** |
| `ATTRIBUTE_TREE=5015997` | **258** |

It is silently broken (callers get all ads back believing they filtered), and the
only test covering it (`tests/test_search.py`) asserts the param *mapping*, not
the API *effect* — green but meaningless. Decision: **remove** `category_id` and
**add** a working `category` kwarg mapping to `ATTRIBUTE_TREE`. Blast radius is
~zero: `willhaben-app`'s marktplatz form does not pass `category_id`.

## Design

### Approach: single `navigate()` returning a bundle (Option A)

One free function returns one immutable `NodeView` holding breadcrumbs, child
categories, and filters — all from a single request, since the API returns them
together. Chosen over separate `subcategories()`/`filters()` functions (would
double requests for the one screen that needs both) and a stateful `Navigator`
object (its in-memory cache/connection reuse is wasted in a per-request Flask /
Celery consumer, and it breaks the package's free-function + frozen-dataclass
idiom). A thin `Navigator` wrapper can be added later if REPL ergonomics are
wanted; shipping A costs nothing toward that.

### Module & public surface

New module `src/willhaben/navigation.py`. New exports in `__init__.py`:
`navigate`, `NodeView`, `Category`, `Filter`, `FilterValue`, `Crumb`,
`FilterType`, `SelectionMode`.

### Data model (all `@dataclass(frozen=True, slots=True)`)

```python
class FilterType(StrEnum):       # normalized from navigatorType
    RANGE = "RANGE"
    SELECT = "SELECT"            # STANDARD navigators
    HIERARCHICAL = "HIERARCHICAL"
    TEXT = "TEXT"                # TEXT_SEARCH (e.g. keyword)

class SelectionMode(StrEnum):    # from navigatorSelectionType
    SINGLE = "SINGLE"
    MULTI = "MULTI"

class FilterValue:
    label: str          # "256 GB"
    value: str          # "2537"  -> goes straight into the URL param
    hits: int | None    # result count if the API provided one

class Filter:
    id: str                       # navigator id, e.g. "Speicherkapazität"
    label: str
    params: tuple[str, ...]       # ("treeAttributes",) or ("PRICE_FROM","PRICE_TO")
    type: FilterType
    selection: SelectionMode
    values: tuple[FilterValue, ...]

class Category:
    id: int             # ATTRIBUTE_TREE id, e.g. 5015997
    label: str
    hits: int | None

class Crumb:
    label: str
    node_id: int | None           # parsed from trailing "-<id>" in the seo url

class NodeView:
    node_id: int | None
    rows_found: int
    breadcrumbs: tuple[Crumb, ...]
    categories: tuple[Category, ...]   # children; () at a leaf
    filters: tuple[Filter, ...]        # every non-category navigator
```

### `navigate()`

```python
def navigate(node: int | None = None, *, client: WillhabenClient | None = None) -> NodeView:
    client = client or WillhabenClient()
    params: dict[str, str | int] = {"rows": 1}
    if node is not None:
        params["ATTRIBUTE_TREE"] = node
    return NodeView.from_api(client.search(MARKETPLACE_PATH, params), node_id=node)
```

### Parsing rules (`NodeView.from_api`)

Walk `navigatorGroups[].navigatorList[]`:

- The **`category`** navigator (`id == "category"`) → `categories`. For each
  value, read the int id from `urlParamRepresentationForValue` where
  `urlParameterName == "ATTRIBUTE_TREE"`, plus `label` and `hits`.
- **Every other** navigator → a `Filter`:
  - `params` from `urlConstructionInformation.urlParams[].urlParameterName`
    (preserves the two-element `("PRICE_FROM","PRICE_TO")` for ranges).
  - `type` normalized from `navigatorType` (`TEXT_SEARCH` → `TEXT`,
    `STANDARD` → `SELECT`, `RANGE`/`HIERARCHICAL` passthrough).
  - `selection` normalized from `navigatorSelectionType`
    (`SINGLE_SELECT` → `SINGLE`, `MULTI_SELECT` → `MULTI`).
  - values from flat `possibleValues` **or** nested `groupedPossibleValues[].possibleValues`,
    each mapped to a `FilterValue(label, value, hits)` where `value` comes from
    the value's `urlParamRepresentationForValue`.
- `breadcrumbs` from `raw["breadcrumbs"]`: `label` from `displayName`, `node_id`
  by regex of a trailing `-<digits>` in `seoUrl` (`None` for roots like
  "Startseite"/"Marktplatz").
- `rows_found` from `raw["rowsFound"]`.
- Missing/empty `navigatorGroups` → empty tuples (a bad/leaf node must not crash).

### Client fix (`client.py`) — repeated params

`WillhabenClient.search` currently builds `query = {k: str(v) …}`, which cannot
express repeated keys. Change it to build a **list of `(key, str)` pairs**,
expanding list/tuple values into repeats, and pass that to httpx:

```python
pairs: list[tuple[str, str]] = []
for k, v in params.items():
    if v is None:
        continue
    if isinstance(v, (list, tuple)):
        pairs.extend((k, str(x)) for x in v)
    else:
        pairs.append((k, str(v)))
```

Enables multi-select facets (`treeAttributes`) and multi-`areaId`; backward
compatible for scalar params. `isNavigation=true` default is preserved.

### Search integration — replace `category_id`

In `search.py`, `_build_params` / `search` / `count` / `iter_ads`:

- Remove the `category_id` parameter and its `params["categoryId"] = …` mapping.
- Add `category: int | None = None`, mapping to `params["ATTRIBUTE_TREE"] = category`.

No other signature changes. A fully-composed tracked search remains expressible
via `extra_params`, now including list values:

```python
willhaben.search(category=5015997,
                 extra_params={"treeAttributes": [2537, 2540], "PRICE_TO": 900})
```

The package provides no selection→params helper (YAGNI): building the dict from
selected filters is `{filter.params[0]: [v.value, …]}`, which belongs in the app
layer.

## Error handling

- Network/HTTP failures propagate as the existing `WillhabenAPIError`.
- A node id with no children (a leaf) yields `categories == ()` and a populated
  `filters` — normal, not an error.
- Absent `navigatorGroups`/`breadcrumbs` keys parse to empty tuples rather than
  raising.

## Testing

- **Fixtures**: capture trimmed live responses keeping `navigatorGroups` +
  `breadcrumbs` + `rowsFound`. Three nodes, each chosen so every assertion below
  is grounded in a node where that fact was verified live:
  - `tests/fixtures/navigate_root.json` (node `None`) — top-level categories.
  - `tests/fixtures/navigate_apple.json` (node 2724) — an intermediate node with
    child categories.
  - `tests/fixtures/navigate_iphone.json` (node 5015997) — a leaf with no child
    categories but the full facet set.
- **Unit (`tests/test_navigation.py`)**, parsing the fixtures:
  - Root: ~19 top-level categories present.
  - Apple (2724): `categories` includes `Category(id=5015997, label="iPhone 17 Pro")`.
  - iPhone leaf (5015997): `categories == ()`; the `Speicherkapazität` filter has
    `params == ("treeAttributes",)`, `selection == MULTI`, non-empty `values`;
    the `price` filter has `params == ("PRICE_FROM", "PRICE_TO")`, `type == RANGE`.
  - breadcrumbs parse to the expected labels/ids; root crumbs have `node_id is None`.
- **Client unit (`tests/test_client.py`)**: a list-valued param emits repeated
  query keys (assert via a stub httpx transport / captured request URL).
- **Search unit (`tests/test_search.py`)**: update for `category` →
  `{"ATTRIBUTE_TREE": …}`; drop the `categoryId` assertion.
- **Live (`@pytest.mark.live`, `tests/test_live.py`)**:
  - `navigate(None)` returns the known top-level categories with stable ids
    (drift check, mirroring the existing area-hierarchy drift test).
  - `count(category=2691)` is strictly less than `count()` — guards against the
    "mapping works but API ignores the param" class of bug that hid the
    `categoryId` breakage.

## Out of scope

- `willhaben-app` changes (drill-down UI, dynamic form, JSONB schema/validation,
  unique-constraint implications) — separate spec.
- Real-estate / motor verticals (the same `navigatorGroups` mechanism applies,
  but this spec targets the marketplace tree behind the iPhone example).
- Caching / short-TTL of node responses — a later optimization; `navigate()` is
  one live request per call by design.
- A stateful `Navigator` convenience wrapper.
- Investigating whether `categoryId` is meaningful on any *other* endpoint.

## Appendix: verified category path (the iPhone example)

```
marktplatz (root, ATTRIBUTE_TREE unset)
 └─ Smartphones / Telefonie   id=2691
     └─ Smartphones / Handys  id=2722
         └─ Apple             id=2724
             └─ iPhone 17 Pro id=5015997   (the "5015997" in the example URL)
```

`treeAttributes=2537` from the example URL is one value of one facet
(Speicherkapazität / Zustand / …) at the leaf; its id is present in that node's
`navigate()` filter values.
