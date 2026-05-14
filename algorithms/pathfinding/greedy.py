"""
algorithms/pathfinding/greedy.py — Greedy Best-First Search.

Like A* but with g = 0. Only cares about how close a cell is to the goal,
not how far it traveled to get there. Charges through mud because it has
no cost model. Fast, but the path quality suffers for it.
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
    """Greedy Best-First (f = h only)."""
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
            yield {
                "type":    "done",
                "result":  RunResult(steps, pure_time, path_len, path_cost),
                "message": (
                    f"✅ SOLVED! | Steps: {int(steps)} | "
                    f"Time: {pure_time * 1000:.2f} ms | "
                    f"Path: {path_len} | Cost: {path_cost}"
                ),
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

        # PQ Inspector — top-3 entries by h value
        pq_info = ""
        if pq:
            top     = heapq.nsmallest(min(3, len(pq)), pq)
            pq_info = "  │  ".join(f"({pr},{pc}) h={h}" for h, (pr, pc) in top)

        yield {
            "type":    "step",
            "r": r, "c": c,
            "steps":   steps,
            "title":   "Greedy (Cost-Blind)",
            "restore": ".",
            "pq_info": pq_info,
        }

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ Greedy: no path found.",
    }
