"""
core/grid.py — directions, passability, and terrain costs.

Shared by all four modules. Used to be duplicated everywhere.
"""
from __future__ import annotations


# Cardinal direction offsets: right, down, left, up
DIRECTIONS: tuple[tuple[int, int], ...] = ((0, 1), (1, 0), (0, -1), (-1, 0))

# Cell values a classic pathfinding agent can enter.
# dynamic_gen3 uses a wider set that also includes 'S' and 'T' for its own reasons.
# Don't merge them — the contexts are different.
PASSABLE: frozenset[int | str] = frozenset({0, 'S', 'E', '~'})


def terrain_cost(cell: int | str) -> int:
    """Return the movement cost of entering a cell. Mud costs 3, everything else costs 1."""
    return 3 if cell == '~' else 1


def is_wall(cell: int | str) -> bool:
    """Return True if the cell blocks movement entirely."""
    return cell == 1
