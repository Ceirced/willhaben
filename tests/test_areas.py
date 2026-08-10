from __future__ import annotations

from willhaben.constants import AREAS, AREAS_BY_ID, Area


def test_area_defaults() -> None:
    a = Area(id=1, name="Burgenland")
    assert a.id == 1
    assert a.name == "Burgenland"
    assert a.parent is None
    assert a.children == ()


def test_area_equality_is_identity() -> None:
    # Two Areas with identical fields must NOT compare equal — equality is
    # by identity so a tree with cyclic parent/child refs doesn't recurse
    # through `__eq__`.
    a = Area(id=1, name="Burgenland")
    b = Area(id=1, name="Burgenland")
    assert a is not b
    assert a != b
    assert a == a


def test_area_repr_excludes_parent() -> None:
    parent = Area(id=1, name="Burgenland")
    child = Area(id=101, name="Eisenstadt", parent=parent)
    text = repr(child)
    assert "Eisenstadt" in text
    assert "parent=" not in text


def test_area_children_is_settable_after_construction() -> None:
    # Required because the tree builder constructs the parent first, then
    # creates children that reference it, then assigns the children tuple
    # back onto the parent.
    state = Area(id=1, name="Burgenland")
    child = Area(id=101, name="Eisenstadt", parent=state)
    state.children = (child,)
    assert state.children == (child,)
    assert state.children[0].parent is state


def test_areas_has_ten_top_level_entries() -> None:
    assert len(AREAS) == 10


def test_top_level_areas_have_no_parent() -> None:
    for area in AREAS.values():
        assert area.parent is None


def test_every_top_level_area_has_children() -> None:
    # Including "andere länder", whose children are foreign countries.
    for slug, area in AREAS.items():
        assert len(area.children) > 0, f"{slug} has no children"


def test_children_parent_back_reference() -> None:
    for area in AREAS.values():
        for child in area.children:
            assert child.parent is area


def test_areas_by_id_round_trip() -> None:
    for area in AREAS.values():
        assert AREAS_BY_ID[area.id] is area
        for child in area.children:
            assert AREAS_BY_ID[child.id] is child


def test_areas_by_id_has_149_nodes() -> None:
    # 10 top-level + 116 Austrian districts + 23 foreign countries.
    assert len(AREAS_BY_ID) == 149


def test_negative_ids_only_under_andere_laender() -> None:
    andere = AREAS["andere länder"]
    for area in AREAS_BY_ID.values():
        if area.id < 0:
            assert area.parent is andere, (
                f"{area.name} ({area.id}) has negative id but parent is "
                f"{area.parent.name if area.parent else None!r}"
            )


def test_known_lookups() -> None:
    # Spot-check a few IDs the spec mentions, to catch silent reshuffles.
    assert AREAS_BY_ID[900].name == "Wien"
    assert AREAS_BY_ID[101].name == "Eisenstadt"
    assert AREAS_BY_ID[101].parent is AREAS["burgenland"]
    assert AREAS_BY_ID[-137].name == "Deutschland"
    assert AREAS_BY_ID[-137].parent is AREAS["andere länder"]
