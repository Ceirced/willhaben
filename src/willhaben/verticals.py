from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .constants import MARKETPLACE_PATH


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


MARKETPLACE: Final = Vertical(
    name="marketplace",
    root_path=MARKETPLACE_PATH,
    node_param="ATTRIBUTE_TREE",
    node_path=None,
    category_nav="category",
)
REALESTATE: Final = Vertical(
    name="realestate",
    root_path="atz/seo/immobilien/immobilien",
    node_param=None,
    node_path="atz/2/{node}",
    category_nav="searchId",
)
AUTO: Final = Vertical(
    name="auto",
    root_path="atz/seo/gebrauchtwagen/auto",
    node_param=None,
    node_path="atz/3/{node}",
    category_nav="searchId",
)


def _target(vertical: Vertical, node: int | None) -> tuple[str, dict[str, int]]:
    """Resolve `(path, extra_query_params)` for a vertical + optional node."""
    if node is None:
        return vertical.root_path, {}
    if vertical.node_param is not None:
        return vertical.root_path, {vertical.node_param: node}
    if vertical.node_path is not None:
        return vertical.node_path.format(node=node), {}
    raise ValueError(f"{vertical.name} cannot scope to a node yet")
