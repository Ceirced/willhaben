from __future__ import annotations

from willhaben.constants import Area


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
