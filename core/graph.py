"""
core/graph.py — distance calculations and path utilities.

Shared across all solver modules. No side effects.
"""
from __future__ import annotations

import collections
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.types import RunResult


def manhattan_distance(p1: tuple[int, int], p2: tuple[int, int]) -> int:
    """Manhattan distance between two grid positions.

    Used as the A* / Greedy heuristic. Admissible on this grid because
    the minimum step cost is 1, so it never overestimates.
    """
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


# Short alias used in multi_agent_solver
manhattan = manhattan_distance


def validate_path(
    maze:       list[list[int | str]],
    path_len:   int,
    path_cost:  int,
) -> str | None:
    """Check that the path the algorithm stamped on the maze is physically valid.

    reconstruct_path_cells marks every intermediate cell as 'P'. S and E keep
    their original markers. path_len counts those 'P' cells — S and E not
    included.

    Returns None when everything looks right, or a short description of what
    went wrong.

    A full BFS through 'P' cells is unreliable here because the animation loop
    leaves explored-but-discarded cells as '.' — the same value that some path
    cells temporarily hold before the reconstruction pass. Instead we check three
    things that are robust against whatever state the animation left the maze in:

      1. Count of 'P' cells == path_len.
      2. S has at least one 'P' or 'E' neighbour — path leaves the start.
      3. E has at least one 'P' or 'S' neighbour — path arrives at the end.
    """
    if path_len == 0:
        return None  # no path claimed — nothing to check

    rows, cols = len(maze), len(maze[0])
    dirs       = [(-1, 0), (0, 1), (1, 0), (0, -1)]

    start = end = None
    for r in range(rows):
        for c in range(cols):
            v = maze[r][c]
            if v == 'S':
                start = (r, c)
            elif v == 'E':
                end = (r, c)

    if start is None:
        return "S not found in maze"
    if end is None:
        return "E not found in maze"

    # Count 'P' cells — must match what the algorithm reported
    p_cells = sum(1 for r in range(rows) for c in range(cols) if maze[r][c] == 'P')
    if p_cells != path_len:
        return f"P-cell count {p_cells} ≠ reported path_len {path_len}"

    # Terrain costs at least 1 per cell
    if path_cost < path_len:
        return (f"path_cost {path_cost} < path_len {path_len} "
                f"— impossible unless terrain_cost is broken")

    def _adj(pos: tuple[int, int]) -> list[int | str]:
        r, c = pos
        return [
            maze[r + dr][c + dc]
            for dr, dc in dirs
            if 0 <= r + dr < rows and 0 <= c + dc < cols
        ]

    if 'P' not in _adj(start) and 'E' not in _adj(start):
        return "no P cell adjacent to S — path does not leave the start"

    if 'P' not in _adj(end) and 'S' not in _adj(end):
        return "no P cell adjacent to E — path does not reach the end"

    return None


def _deduplicate_path(
    history: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Remove loops from a traversal history in O(n) time.

    When the agent visits a cell it's already been to, everything between
    the two visits is a loop — we cut it out. This repeats until there are
    no more loops, giving a physically walkable path with no teleportation.

    Example:
        history = [S, A, B, C, A, D, E]   # agent looped A → B → C → A
        result  = [S, A, D, E]             # loop B → C removed at re-entry of A

    Important: the naive "keep first occurrence" approach produces [S, A, B, C, D, E]
    which has a C→D teleportation gap (they're not adjacent). Loop-truncation is
    the correct fix.
    """
    path:     list[tuple[int, int]]       = []
    seen_idx: dict[tuple[int, int], int]  = {}

    for pos in history:
        if pos in seen_idx:
            idx = seen_idx[pos]
            # Remove everything after the first visit to this cell
            for removed in path[idx + 1:]:
                del seen_idx[removed]
            path = path[:idx + 1]
        else:
            seen_idx[pos] = len(path)
            path.append(pos)

    return path