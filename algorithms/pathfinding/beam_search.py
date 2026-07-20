"""
algorithms/pathfinding/beam_search.py
--------------------------------------
Beam Search — heuristic-guided with a fixed-width frontier (f = h, width = k).

Generator contract: yields "step" dicts with ``pq_info`` for the PQ Inspector;
yields "done" on completion.  beam_width caps how many nodes survive each round.
"""

from __future__ import annotations

import heapq
import time
from typing import Generator

from core.grid  import DIRECTIONS, PASSABLE
from core.graph import manhattan_distance
from core.types import RunResult

from ._shared import reconstruct_path_cells

# Benchmark skip sentinel — PQ Inspector is disabled above this threshold.
_BENCH_SKIP: int = 999_999


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
    beam_width:  int = 3,
) -> Generator[dict, None, None]:
    """Beam Search on *maze* (f = h, frontier capped at beam_width nodes).

    Expands the best node from the current beam, generates all children,
    merges them with the surviving beam, and prunes back to beam_width
    by Manhattan distance to the goal.

    Key properties
    --------------
    *  **Incomplete**: if the optimal path passes through a node that was
       pruned from the beam, the search misses it and may return no path.
       The wider the beam, the less likely this is.
    *  **Memory-bounded**: the frontier never grows beyond beam_width nodes,
       making it far cheaper than A* or Greedy on large mazes.
    *  **beam_width = 1**: pure greedy hill-climbing — fastest, most likely
       to fail.  beam_width = ∞: degenerates to Greedy Best-First.

    The pq_info field carries a top-3 beam snapshot for the PQ Inspector.
    """
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)
    bw = max(1, beam_width)

    beam:    list[tuple[int, tuple[int, int]]] = [
        (manhattan_distance(start, end), start)
    ]
    parent:  dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    visited: set[tuple[int, int]]                          = {start}

    steps        = 0
    compute_time = 0.0

    while beam:
        t0      = time.perf_counter()
        _, curr = heapq.heappop(beam)
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
                heapq.heappush(beam, (manhattan_distance((nr, nc), end), (nr, nc)))

        if len(beam) > bw:
            beam = heapq.nsmallest(bw, beam)
            heapq.heapify(beam)

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        pq_info = ""
        if beam:
            top   = heapq.nsmallest(min(3, len(beam)), beam)
            parts = [f"({pr},{pc}) h={h}" for h, (pr, pc) in top]
            pq_info = "  │  ".join(parts)

        yield {
            "type":    "step",
            "r": r, "c": c,
            "steps":   steps,
            "title":   f"Beam Search (w={bw})",
            "restore": ".",
            "pq_info": pq_info,
            "extra": {
                "algo":       "beam_search",
                "h":          manhattan_distance((r, c), end),
                "beam_width": bw,
                "beam_size":  len(beam),
                "no_logic":   True,
            },
        }

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": f"❌ Beam Search (w={bw}): no path found — beam too narrow.",
    }
