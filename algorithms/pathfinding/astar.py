"""
algorithms/pathfinding/astar.py — A* Search.

The gold standard. f = g(terrain cost) + h(Manhattan distance).
Cost-aware like Dijkstra, but focuses toward the goal like Greedy.
Usually explores far fewer cells than Dijkstra while still finding
the optimal path.
"""
from __future__ import annotations

import heapq
import time
from typing import Generator

from core.grid  import DIRECTIONS, PASSABLE, terrain_cost
from core.graph import manhattan_distance
from core.types import RunResult

from ._shared import reconstruct_path_cells

_BENCH_SKIP: int = 999_999


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """A* (f = g + h)."""
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    pq:         list[tuple[float, tuple[int, int]]]              = [(0.0, start)]
    parent:     dict[tuple[int, int], tuple[int, int] | None]    = {start: None}
    g_score:    dict[tuple[int, int], float]                     = {start: 0.0}
    closed_set: set[tuple[int, int]]                             = set()

    steps        = 0
    compute_time = 0.0

    while pq:
        t0      = time.perf_counter()
        _, curr = heapq.heappop(pq)

        if curr in closed_set:
            compute_time += time.perf_counter() - t0
            continue
        closed_set.add(curr)

        r, c = curr
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
            if 0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] in PASSABLE:
                new_g = g_score[curr] + terrain_cost(maze[nr][nc])
                if (nr, nc) not in g_score or new_g < g_score[(nr, nc)]:
                    g_score[(nr, nc)] = new_g
                    f_score           = new_g + manhattan_distance((nr, nc), end)
                    parent[(nr, nc)]  = curr
                    heapq.heappush(pq, (f_score, (nr, nc)))

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        # Compute h fresh — don't use (f - g) from the heap entry, those are stale.
        pq_info = ""
        if pq:
            top   = heapq.nsmallest(min(3, len(pq)), pq)
            parts = []
            for f, (pr, pc) in top:
                g = g_score.get((pr, pc), 0)
                h = manhattan_distance((pr, pc), end)
                parts.append(f"({pr},{pc}) g={g:.0f} h={h} f={g + h:.0f}")
            pq_info = "  │  ".join(parts)

        yield {
            "type":    "step",
            "r": r, "c": c,
            "steps":   steps,
            "title":   "A* (Cost-Aware)",
            "restore": ".",
            "pq_info": pq_info,
        }

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ A*: no path found.",
    }
