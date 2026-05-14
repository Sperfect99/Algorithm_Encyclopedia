"""
Pathfinding helpers shared by all 15 algorithm files.

Path reconstruction and cell marking — common logic that'd otherwise
live in every single algorithm file.
"""
from __future__ import annotations

from core.grid  import terrain_cost
from core.graph import _deduplicate_path
from core.types import RunResult


def reconstruct_path_cells(
    parent:    dict[tuple[int, int], tuple[int, int] | None],
    end:       tuple[int, int],
    maze:      list[list[int | str]],
    fog:       set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """Walk the parent dict backwards from end → start, stamp cells 'P'.

    Returns (path_len, path_cost). S and E cells don't count toward either.
    """
    path_len  = 0
    path_cost = 0
    curr: tuple[int, int] | None = end

    while curr is not None:
        r, c = curr
        if maze[r][c] not in {'S', 'E'}:
            path_cost += terrain_cost(maze[r][c])
            maze[r][c]  = 'P'
            path_len   += 1
            if fog is not None:
                fog.add((r, c))
        curr = parent.get(curr)

    return path_len, path_cost


def wall_follower_path_cells(
    history:   list[tuple[int, int]],
    maze:      list[list[int | str]],
    fog:       set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """Take a position history, deduplicate loops out of it, then stamp 'P'.

    Used by all the wall-follower variants that track history instead of a parent dict.
    """
    final_path = _deduplicate_path(history)
    path_len   = 0
    path_cost  = 0

    for pr, pc in final_path:
        if maze[pr][pc] not in {'S', 'E'}:
            path_cost += terrain_cost(maze[pr][pc])
            maze[pr][pc] = 'P'
            path_len    += 1
            if fog is not None:
                fog.add((pr, pc))

    return path_len, path_cost
