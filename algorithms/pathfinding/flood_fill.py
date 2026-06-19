"""
algorithms/pathfinding/flood_fill.py
--------------------------------------
Flood Fill — reachability mapping from S, no target.

Generator contract: yields "step" dicts during expansion;
yields "done" once all reachable cells are flooded.

Unlike every other algorithm in this suite, Flood Fill has no
target.  It maps the entire connected component that contains S,
stamping each reachable cell with 'P' and recording how many BFS
steps it took to reach that cell.  This makes it useful for
visualising the shape of the maze's reachable space rather than
finding a single path through it.
"""

from __future__ import annotations

import time
from collections import deque
from typing      import Generator

from core.grid  import DIRECTIONS, PASSABLE, terrain_cost
from core.types import RunResult


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """Flood Fill on *maze* — maps every reachable cell from S.

    Expands outward from S in BFS order with no target cell.  Every
    passable cell in the connected component that contains S is
    eventually reached and stamped 'P'.  Walls and unreachable cells
    are left untouched.

    Key properties
    --------------
    *  **No path**: Flood Fill does not find a path to E.  path_len
       reports the number of reachable cells; path_cost is their
       total terrain cost.  E is treated as just another cell.
    *  **Completeness**: every cell reachable from S is visited
       exactly once, in non-decreasing hop order.
    *  **Micromouse**: the algorithm underpins the classic micromouse
       competition strategy — flood the maze from the goal to build a
       distance map, then follow the gradient back to start.

    Yields:
        ``{"type": "step", ...}`` for every cell flooded.
        ``{"type": "done", ...}`` once all reachable cells are stamped.
    """
    rows, cols = len(maze), len(maze[0])
    start      = (0, 0)

    queue:   deque[tuple[int, int]]                         = deque([start])
    visited: set[tuple[int, int]]                           = {start}
    dist:    dict[tuple[int, int], int]                     = {start: 0}

    steps        = 0
    compute_time = 0.0
    path_len     = 0
    path_cost    = 0

    while queue:
        t0   = time.perf_counter()
        curr = queue.popleft()
        r, c = curr

        for dr, dc in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < rows and 0 <= nc < cols
                and maze[nr][nc] in PASSABLE
                and (nr, nc) not in visited
            ):
                visited.add((nr, nc))
                dist[(nr, nc)] = dist.get(curr, 0) + 1
                queue.append((nr, nc))

        if maze[r][c] not in {'S', 'E'}:
            path_cost   += terrain_cost(maze[r][c])
            path_len    += 1

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        yield {
            "type":    "step",
            "r": r, "c": c,
            "steps":   steps,
            "title":   "Flood Fill",
            "restore": "P",
            "pq_info": "",
            "extra": {
                "algo":      "flood_fill",
                "dist":      dist.get(curr, 0),
                "filled":    steps,
                "no_logic":  True,
            },
        }

    msg = (
        f"✅ Flood Fill complete | Steps: {steps} | "
        f"Time: {compute_time * 1000:.2f} ms | "
        f"Cells reached: {path_len} | Cost: {path_cost}"
    )
    yield {
        "type":    "done",
        "result":  RunResult(steps, compute_time, path_len, path_cost),
        "message": msg,
    }