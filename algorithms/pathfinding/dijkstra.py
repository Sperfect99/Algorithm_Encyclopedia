"""
algorithms/pathfinding/dijkstra.py
-----------------------------------
Dijkstra's Algorithm — Uniform Cost Search (A* with h = 0).

Generator contract: yields "step" dicts with ``pq_info`` for the V6 PQ
Inspector; yields "done" on completion.
"""

from __future__ import annotations

import heapq
import time
from typing import Generator

from core.grid  import DIRECTIONS, PASSABLE, terrain_cost
from core.types import RunResult

from ._shared import reconstruct_path_cells


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """
    Dijkstra's Algorithm on *maze* (f = accumulated terrain cost only).

    Explores radially from start; always expands the cheapest-known node.
    Cost-aware: routes around mud (cost 3).  Equivalent to A* with h = 0.

    The ``pq_info`` field carries a top-3 heap snapshot for the V6 PQ Inspector.

    Yields:
        ``{"type": "step", ..., "pq_info": str}`` for every node expanded.
        ``{"type": "done", ...}`` once solved or heap exhausted.
    """
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    pq: list[tuple[float, tuple[int, int]]]              = [(0.0, start)]
    parent:     dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    g_score:    dict[tuple[int, int], float]                  = {start: 0.0}
    closed_set: set[tuple[int, int]]                          = set()

    steps        = 0
    compute_time = 0.0

    while pq:
        t0      = time.perf_counter()
        g, curr = heapq.heappop(pq)

        if curr in closed_set:
            compute_time += time.perf_counter() - t0
            continue
        closed_set.add(curr)

        r, c = curr
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
            if 0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] in PASSABLE:
                new_g = g_score[curr] + terrain_cost(maze[nr][nc])
                if (nr, nc) not in g_score or new_g < g_score[(nr, nc)]:
                    g_score[(nr, nc)] = new_g
                    parent[(nr, nc)]  = curr
                    heapq.heappush(pq, (new_g, (nr, nc)))

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        # V6 PQ Inspector — top-3 entries shown as "(row,col) g=G"
        pq_info = ""
        if pq:
            top   = heapq.nsmallest(min(3, len(pq)), pq)
            parts = [f"({pr},{pc}) g={gv:.0f}" for gv, (pr, pc) in top]
            pq_info = "  │  ".join(parts)

        yield {
            "type":    "step",
            "r": r, "c": c,
            "steps":   steps,
            "title":   "Dijkstra (Uniform Cost)",
            "restore": ".",
            "pq_info": pq_info,
            "extra": {"algo": "dijkstra", "g": g_score.get(curr, 0),
                      "open_size": len(pq), "closed_size": len(closed_set)},
        }

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ Dijkstra: no path found.",
    }