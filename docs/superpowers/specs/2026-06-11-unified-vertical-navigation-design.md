# Unified, data-driven vertical navigation, filter discovery & search

**Date:** 2026-06-11
**Status:** Approved design, ready for implementation plan
**Scope:** the `willhaben` package only. The `willhaben-app` wiring (Order
build-UI, persistence/JSONB, reconciliation of saved Orders) is out of scope —
the package returns the live truth; the app decides what to do with it.
**Builds on / supersedes:** `2026-06-05-runtime-category-filter-discovery-design.md`,
which added `navigate()` for marketplace.

## Problem

The package exposes `navigate()` (discovery) and `search()`/`count()` (ad
fetching) as two things, and the fetch functions hardcode willhaben's domain
into their signatures: `keyword`, `price_from`, `price_to`, `area_id`,
`category`, `is_private`, `property_type`, `rooms`, `area_m2_from/to`,
`misc_category`, `offer_type`, plus hand-written validation (`misc_category`
only valid on `OTHER`, …). Every one of these is something willhaben already
describes at runtime in the `navigatorGroups` of every response.

**Goal:** one coherent, data-driven flow across **marketplace, realestate, and
auto**. Filtering parameters are not function arguments — they are *discovered*
from the response and *applied* through a declarative selection dict. The
function surface keeps
only mechanical concerns (pagination, sort, HTTP client). A "search agent" /
**Order** (a category + filters, used to analyse the ads under it) is then a
fully generic, persistable value with no vertical-specific code behind it.

## Verified findings (live `rows=1` probes)

**All three verticals expose discoverable categories — via two navigator
mechanisms — plus filters.**

| Vertical | Root path | Category navigator | Node applied via |
| --- | --- | --- | --- |
| Marketplace | `atz/seo/kaufen-und-verkaufen/marktplatz` | `category` (HIERARCHICAL, deep tree) | `ATTRIBUTE_TREE` **query param** |
| Realestate | `atz/seo/immobilien/immobilien` | `searchId` (STANDARD, flat list) | **path** `atz/2/<id>` |
| Auto | `atz/seo/gebrauchtwagen/auto` | `searchId` (STANDARD, flat list) | **path** `atz/3/<id>` |

The `searchId` navigator lists each category with a human-readable label and an
id (`Haus kaufen → 102`, `Wohnung kaufen → 101`, …) — these ids equal the legacy
`RealEstateCategory` enum and scope correctly through the path (`atz/2/102` →
Haus kaufen). **So categories are discovered for every vertical**, and the
hardcoded `RealEstateCategory`/`EstateMiscCategory`/`OfferType` enums are
redundant snapshots that we drop. Marketplace drills a deep tree; realestate/auto
expose a flat top-level list. Auto additionally narrows via `make → model`
hierarchical filters.

**Two `searchId` caveats:** (1) `searchId` scopes only through the path — passing
it as a query param is silently ignored (the `categoryId`-class trap), so the
node id goes in the path per the vertical's strategy. (2) The realestate **root**
(category listing) is at `atz/seo/immobilien/immobilien`, a different path from a
scoped node (`atz/2/<id>`), so a vertical needs a distinct root path.

**Every filter value is self-describing.** Each `possibleValue` carries its own
`urlParamRepresentationForValue` — the exact param(s) and value(s) to send.
Confirmed across kinds:

- Discrete (`Zustand`, `Speicherkapazität`): one param, e.g. `treeAttributes=2537`.
- Bucketed range (`mileage`, `batterycapacity`): the bucket carries **both**
  bounds, e.g. `'10.000 – 49.999' → MILEAGE_FROM=10000, MILEAGE_TO=49999`.
- Free-form range (`price`): `type=RANGE`, params `(PRICE_FROM, PRICE_TO)`,
  **zero** values — you supply raw numbers.
- Text (`keyword`): `type=TEXT_SEARCH`, param `keyword`, zero values.

So **selecting any value = emitting that value's own representation** — one code
path for discrete and bucketed-range filters alike. Only value-less filters
(free-form ranges, text) need a typed input rather than a pick.

**Every current domain kwarg is a discoverable navigator** (verified params):
`is_private→dealer(ISPRIVATE)`, `area_id→state/province(areaId)`,
`keyword→keyword(keyword)`, `misc_category→objecttype(ESTATE_MISC_CATEGORY)`,
`offer_type→ownagetype(OWNAGETYPE)`, `price→price(PRICE_FROM,PRICE_TO)`. The
`misc_category`/`offer_type` "only on OTHER" rule is enforced by the data — those
navigators appear only on the OTHER node — so the hand-written guards are deleted.

**Dependencies are data-driven.** Auto `model` is `NOT_SELECTABLE` with zero
values until a `make` is selected; re-requesting with `CAR_MODEL/MAKE=1005`
populates it. The response for the current selections is the source of truth.

**Filters ride on every response.** `navigate`/`count`/`search` hit the same
endpoint; every response carries `navigatorGroups` and ads (differing only by
`rows`). Discovery never costs a request separate from a count/search.

**One caveat — discovered values can be a subset of the param's domain.** The
`state` navigator lists only the 10 Bundesländer, but `areaId` accepts the 138
district ids in `AREAS_BY_ID`. So selection must allow a raw param value (the
`extra` hatch), not only a pick from discovered values.

## Design

### The data model

```python
@dataclass(frozen=True, slots=True)
class Vertical:
    name: str
    root_path: str             # path when node is None (lists categories)
    node_param: str | None     # query-param for the node ("ATTRIBUTE_TREE") on root_path, else None
    node_path: str | None      # path template "atz/2/{node}" when the node scopes via the path, else None
    category_nav: str          # navigator id holding categories: "category" or "searchId"

MARKETPLACE = Vertical("marketplace", "atz/seo/kaufen-und-verkaufen/marktplatz", "ATTRIBUTE_TREE", None,         "category")
REALESTATE  = Vertical("realestate",  "atz/seo/immobilien/immobilien",          None,            "atz/2/{node}", "searchId")
AUTO        = Vertical("auto",         "atz/seo/gebrauchtwagen/auto",            None,            "atz/3/{node}", "searchId")

@dataclass(frozen=True, slots=True)
class Order:
    """A persistable, replayable search agent: where + what."""
    vertical: Vertical
    node: int | None             # catalog coordinate (None = vertical root)
    params: Mapping[str, QueryValue]   # the flat willhaben URL params (the filters)
```

`node` is the catalog **coordinate**, not a filter — structural, set by
*navigating*, not by `select`. Resolution:

```python
def _target(vertical: Vertical, node: int | None) -> tuple[str, dict[str, int]]:
    if node is None:
        return vertical.root_path, {}
    if vertical.node_param:                       # marketplace: query param on root path
        return vertical.root_path, {vertical.node_param: node}
    if vertical.node_path:                        # realestate: node in the path
        return vertical.node_path.format(node=node), {}
    raise ValueError(f"{vertical.name} cannot scope to a node yet")
```

`Filter` gains `available: bool` (False when `navigatorSelectionType == NOT_SELECTABLE`),
so consumers gate locked filters (auto `model`) until a prerequisite is chosen.
`NodeView` gains `vertical: Vertical`. `categories` is parsed from the navigator
named by `vertical.category_nav` (`category` for marketplace, `searchId` for
realestate/auto) — each `Category` carries the id used by `_target` to scope
(`ATTRIBUTE_TREE` value for marketplace, `searchId` value for the others) plus
its label and hits.

### `navigate()` — discovery (mechanical args only)

```python
def navigate(
    node: int | None = None,
    *,
    vertical: Vertical = MARKETPLACE,
    selections: Mapping[str, QueryValue] | None = None,
    client: WillhabenClient | None = None,
) -> NodeView
```

`selections` is forwarded so the response reflects dependent filters (pass a
chosen `make` to get auto `model` values). One `rows=1` request.

### Building an Order — the view resolves selections (no builder object)

A `NodeView` knows its vertical, node, and the filters valid there, so it turns
a declarative dict of human-readable selections into a validated `Order`. No
stateful builder, no method chaining — one call in, one `Order` out:

```python
view = willhaben.navigate(2724)          # marketplace Apple node

order = view.order(
    select={
        "Zustand": ["Neu", "Gut"],             # list  → discrete pick(s); MULTI stacks
        "Speicherkapazität": ["256 GB"],
        "mileage": "10.000 – 49.999",          # bucketed range = a normal pick
        "price": (100, 900),                   # tuple → free-form range → (FROM, TO)
        "keyword": "macbook air",              # str   → TEXT filter
    },
    extra={"areaId": 900},                     # raw param escape hatch (a district id)
)                                              # -> Order(vertical, node, params)

count(order)                                   # int
search(order, rows=50, sort=SortOrder.PRICE_ASC)
iter_ads(order, max_results=200)

# conveniences that resolve + execute in one step:
view.count(select={...})
view.search(select={...}, sort=SortOrder.PRICE_ASC, rows=50)
```

`view.order(select, extra)` resolves each entry by **filter** (looked up by
label/id in `view.filters`), dispatching on the filter's **type** (the value's
Python type only disambiguates within RANGE):

- **TEXT** filter → `str` value → `{params[0]: value}`.
- **RANGE** filter → `tuple (lo, hi)` free-form bounds (`None` = open-ended),
  **or** a label / list of labels naming preset bucket(s), resolved like a pick.
- **SELECT/HIERARCHICAL** filter → label or list of labels matched against the
  filter's `values`; emit each value's own `urlParamRepresentationForValue`;
  enforces `SINGLE` vs `MULTI`.

`extra` is the explicit raw-param hatch for values not offered as a discovered
value (district `areaId`, future params). Unknown filter, absent value, locked
(`available == False`) filter, or type mismatch → `ValueError`.

For an interactive click-by-click UI, the app can equivalently accumulate
`params` directly: each rendered `FilterValue` already carries its resolved
param + value, so a click appends to a running dict that is both fed back into
`navigate(selections=…)` (to refresh dependent filters) and saved as
`Order.params`. `view.order(select=…)` is the batch/form-submission convenience
over that same resolution. Resolution is **by label with id fallback**.

### Executing a stored Order (no discovery, no domain args)

```python
def search(order: Order, *, rows: int = 30, page: int = 1,
           sort: SortOrder | int | None = None,
           client: WillhabenClient | None = None) -> SearchResult
def count(order: Order, *, client: WillhabenClient | None = None) -> int
def iter_ads(order: Order, *, max_results: int | None = None,
             sort=None, client=None) -> Iterator[Ad]
```

The *only* non-mechanical argument is the generic `Order`. Internally each builds
`(path, params)` from `order.vertical`/`order.node` via the `Vertical` descriptor
and merges `order.params`. `view.search(...)`/`.count(...)` are thin conveniences
that call `view.order(select=…)` then execute.

### Parser unification

- **One `SearchResult` + one generic `Ad` for every vertical.** The separate
  `RealEstateSearchResult`/`RealEstateAd` are removed; vertical-specific ad fields
  (rooms, living area, …) are reached via `Ad.raw_attributes`. The `Ad` parser
  resolves common fields tolerantly across verticals (e.g. price under
  `PRICE/AMOUNT` *or* `PRICE`), since attribute names differ slightly per vertical
  and ad fields are **not** describable from `navigatorGroups`.
- `SearchResult` gains `node -> NodeView`, parsed lazily from the same `raw`
  payload. One request → ads **and** the facets.
- `models.py` `_state_counts_from_raw` is removed; `counts_by_state` becomes a
  derivation over `node.filters` (the filter whose param is `areaId`), preserving
  the public property.
- `navigate()` is "a `rows=1` request whose ads we ignore," sharing one parser.

### What is removed / kept

- **Removed:** all domain kwargs on `search`/`count`/`iter_ads`; the entire
  `search_realestate`/`count_realestate`/`iter_realestate_ads` surface; the
  `RealEstateCategory`/`EstateMiscCategory`/`OfferType` enums (all now discovered
  — categories via the `searchId` navigator, the latter two as
  `objecttype`/`ownagetype` filter values); the typed `RealEstateAd`/
  `RealEstateSearchResult` (folded into generic `Ad`/`SearchResult` + 
  `raw_attributes`); the OTHER-only `ValueError` guards. **Breaking change** —
  ships as a major version bump, no deprecated shims.
- **Kept as reference data (not function args):** `AREAS`/`AREAS_BY_ID` (resolve
  area ids for `extra={"areaId": …}`, since the `state` navigator lists only the
  10 Bundesländer) and `SortOrder` (mechanical sort). Categories for **every**
  vertical come from `view.categories`; no category enum is retained.
- **Mechanical kwargs that stay:** `rows`, `page`, `sort`, `client`,
  `max_results`. These are not filters and are not in `navigatorGroups`.

### Intentionally retained hardcoding

Three islands of willhaben-specific knowledge stay hardcoded **by necessity**,
not oversight — none is discoverable from a response:

1. **Entry points & transport** — `API_ROOT`, `X_WH_CLIENT`, user-agent, and the
   `Vertical` descriptors (each `root_path`, the `atz/2/{node}` template, the
   `ATTRIBUTE_TREE` param, `category_nav`). You cannot bootstrap discovery without
   a known way in; taxonomy/listing endpoints return 404.
2. **Response-schema vocabulary** — the `navigatorType → FilterType` map and the
   magic strings the parser reads (`MULTI_SELECT`, `NOT_SELECTABLE`,
   `urlParamRepresentationForValue`, `groupedPossibleValues`, `breadcrumbs`,
   `rowsFound`, the `areaId`/`category`/`searchId` navigator ids).
3. **Ad attribute names** — the field map in `Ad.from_api` (`PRICE/AMOUNT`,
   `SEO_URL`, `COORDINATES`, …). Result-field names are **not** in
   `navigatorGroups`, so typed common fields require a hardcoded map; everything
   else is available untyped via `Ad.raw_attributes`.

`AREAS_BY_ID` is a deliberate fourth: the 10 Bundesländer *are* discoverable, but
the 138 districts are not, so the tree is kept for district-level `areaId`.

## Error handling

- Network/HTTP failures → existing `WillhabenAPIError`.
- Missing/empty `navigatorGroups`/`breadcrumbs` → empty tuples (no crash).
- `view.order` with unknown filter, absent value, locked filter, or type
  mismatch → `ValueError`.
- Scoping to a node on a vertical with no node strategy yet → `ValueError`
  from `_target`. `node is None` is **valid** for every vertical (it lists the
  vertical's categories at its root).

## Testing

- **Fixtures**: add `navigate_realestate_root.json` (`searchId` navigator lists
  the 12 categories), `navigate_realestate_other.json` (`objecttype`/`ownagetype`
  present), `navigate_auto.json` (root — `searchId` + `model` `NOT_SELECTABLE`),
  `navigate_auto_bmw.json` (`model` populated).
- **Unit**: `Vertical`/`_target` resolution per vertical (query-param vs path vs
  root); categories parsed from `category` (marketplace) and `searchId`
  (realestate/auto) with correct scoping ids; `Filter.available` from
  `NOT_SELECTABLE`; `view.order` for list/tuple/str incl. MULTI stacking,
  bucketed-range pick, `extra` injection, and every raise path; `Order` shape.
- **Model unit**: `result.node` exposes a `NodeView`; `counts_by_state`
  unchanged after `_state_counts_from_raw` removal.
- **Live (`@pytest.mark.live`)**: realestate `searchId` ids match the discovered
  labels and scope via the path; **a `searchId` passed as a query param does NOT
  scope** (guards the `categoryId`-class trap); auto `model` locked→unlocked via
  `selections`; per vertical, a filtered `count(order)` strictly less than the
  node's unfiltered count.

## Open decisions

None — all resolved.

**Resolved:** selections use the declarative `view.order(select=…, extra=…)`
dict (no stateful builder). `sort` lives on `search`/`iter_ads` only (it
describes the response, not the request); `Order` is filters-only. `area_id`
districts go through `extra` with `AREAS_BY_ID` as reference data. **One generic
`Ad`/`SearchResult` for all verticals** — `RealEstateAd`/`CarAd` are not built;
vertical-specific fields come from `Ad.raw_attributes`. The breaking change ships
as a major version bump with no deprecated shims. Auto/motor categories scope via
`atz/3/{node}` (verticalId 3), parallel to realestate — the searchId comes from
`navigate()`'s category values (confirmed against the `ad-search/searchconfig/3`
config and live counts).

## Out of scope

- `willhaben-app` changes (Order build-UI, persistence, reconciliation).
- A stateful fluent `Navigator`/`browse()` — layerable over this surface later.
- Caching/short-TTL of node responses; a recursive full-tree `walk()`.
- Typed per-vertical ad models (`RealEstateAd`, `CarAd`) — generic `Ad` +
  `raw_attributes` covers vertical-specific fields; add later only if needed.
