"""
algorithms/pathfinding/greedy.py
---------------------------------
Greedy Best-First Search — heuristic-only (f = h, cost-blind).

Generator contract: yields "step" dicts with ``pq_info`` for the V6 PQ
Inspector; yields "done" on completion.
"""

from __future__ import annotations

import heapq
import time
from typing import Generator

from core.grid  import DIRECTIONS, PASSABLE
from core.graph import manhattan_distance
from core.types import RunResult

from ._shared import reconstruct_path_cells


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """
    Greedy Best-First Search on *maze* (f = h only, where h = Manhattan distance).

    Explores nodes in order of their Manhattan distance to the goal,
    always expanding whichever open node is **closest to the destination**
    regardless of how far it already is from the start.  This is
    systematic, heuristic-ordered exploration — not memoryless rushing.

    Key properties
    --------------
    *  **Visited set**: once a cell is added to the open heap, it is also
       added to ``visited`` and will never be re-expanded.  The search is
       complete on finite mazes (it cannot loop).
    *  **Not optimal**: ignores accumulated cost ``g``.  On terrain with
       mud (cost 3) it will march through swamps if that is the straight-
       line direction, whereas A* would route around them.
    *  **Faster than A\***: fewer nodes expanded on average, because the
       heuristic aggressively prunes the frontier — at the cost of path
       quality.

    Contrast with A\*
    -----------------
    A\* uses ``f = g + h``; Greedy uses ``f = h``.  Setting ``g = 0``
    removes the "how far did I travel?" term entirely.  The result is a
    search that is pulled toward the goal like a magnet, but may take a
    longer or more expensive route to get there.

    The ``pq_info`` field carries a top-3 heap snapshot for the PQ Inspector.

    Yields:
        ``{"type": "step", ..., "pq_info": str}`` for every node expanded.
        ``{"type": "done", ...}`` once solved or heap exhausted.
    """
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    pq: list[tuple[int, tuple[int, int]]] = [
        (manhattan_distance(start, end), start)
    ]
    parent:  dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    visited: set[tuple[int, int]]                          = {start}

    steps        = 0
    compute_time = 0.0

    while pq:
        t0      = time.perf_counter()
        _, curr = heapq.heappop(pq)
        r, c    = curr

        if curr == end:
            t1 = time.perf_counter()
            path_len, path_cost = reconstruct_path_cells(parent, curr, maze, fog)
            pure_time = compute_time + (time.perf_counter() - t1)
            msg = (
                f"✅ SOLVED! | Steps: {int(steps)} | "
                f"Time: {pure_time * 1000:.2f} ms | "
                f"Path: {path_len} | Cost: {path_cost}"
            )
            yield {
                "type":    "done",
                "result":  RunResult(steps, pure_time, path_len, path_cost),
                "message": msg,
            }
            return

        for dr, dc in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < rows and 0 <= nc < cols
                and maze[nr][nc] in PASSABLE
                and (nr, nc) not in visited
            ):
                visited.add((nr, nc))
                parent[(nr, nc)] = curr
                heapq.heappush(pq, (manhattan_distance((nr, nc), end), (nr, nc)))

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        # V6 PQ Inspector — top-3 entries shown as "(row,col) h=H"
        pq_info = ""
        if pq:
            top   = heapq.nsmallest(min(3, len(pq)), pq)
            parts = [f"({pr},{pc}) h={h}" for h, (pr, pc) in top]
            pq_info = "  │  ".join(parts)

        yield {
            "type":    "step",
            "r": r, "c": c,
            "steps":   steps,
            "title":   "Greedy (Cost-Blind)",
            "restore": ".",
            "pq_info": pq_info,
            "extra": {"algo": "greedy", "h": manhattan_distance((r, c), end),
                      "open_size": len(pq)},
        }

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ Greedy: no path found.",
    }