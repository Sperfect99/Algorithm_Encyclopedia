"""
algorithms/pathfinding/astar.py
--------------------------------
A* Search — cost-aware, heuristic-guided (f = g + h).

Generator contract: yields "step" dicts with ``pq_info`` populated for the
V6 Priority Queue Inspector; yields "done" on completion.

V7 fix (A-1): h is always computed via manhattan_distance() directly —
never as (f - g) from stale heap entries.

V8: heuristic_fn parameter lets callers swap in any h(r, c, gr, gc, maze)
function — preset or user-written plugin.
"""

from __future__ import annotations

import heapq
import math
import time
from typing import Callable, Generator

from core.grid  import DIRECTIONS, PASSABLE, terrain_cost
from core.graph import manhattan_distance
from core.types import RunResult

from ._shared import reconstruct_path_cells

# Benchmark skip sentinel — PQ Inspector is disabled above this threshold.
_BENCH_SKIP: int = 999_999

# ── Built-in heuristic presets ────────────────────────────────────────────
# Each entry: (label_for_menu, admissible, callable)
# The callable receives (r, c, goal_r, goal_c, maze) and returns float.

def _h_manhattan(r, c, gr, gc, maze):
    return abs(gr - r) + abs(gc - c)

def _h_euclidean(r, c, gr, gc, maze):
    return math.sqrt((gr - r) ** 2 + (gc - c) ** 2)

def _h_chebyshev(r, c, gr, gc, maze):
    # max of row/col delta — valid for 8-dir grids, inadmissible here (4-dir)
    return max(abs(gr - r), abs(gc - c))

def _h_weighted_1_5(r, c, gr, gc, maze):
    return 1.5 * (abs(gr - r) + abs(gc - c))

def _h_weighted_2(r, c, gr, gc, maze):
    return 2.0 * (abs(gr - r) + abs(gc - c))

def _h_zero(r, c, gr, gc, maze):
    # h = 0 degenerates A* into Dijkstra
    return 0.0


HEURISTIC_PRESETS: list[tuple[str, bool, Callable]] = [
    ("Manhattan        |Δr|+|Δc|",               True,  _h_manhattan),
    ("Euclidean        √(Δr²+Δc²)",              True,  _h_euclidean),
    ("Chebyshev        max(|Δr|,|Δc|)",          False, _h_chebyshev),
    ("Weighted ×1.5   1.5 × Manhattan",          False, _h_weighted_1_5),
    ("Weighted ×2.0   2.0 × Manhattan",          False, _h_weighted_2),
    ("Zero  h=0       (becomes Dijkstra)",        True,  _h_zero),
]


def solve(
    maze:         list[list[int | str]],
    fog:          set[tuple[int, int]] | None                  = None,
    visit_count:  dict[tuple[int, int], int] | None            = None,
    heuristic_fn: Callable[[int,int,int,int,list], float] | None = None,
) -> Generator[dict, None, None]:
    """A* Search on maze (f = g(terrain cost) + h).

    heuristic_fn — optional callable(r, c, goal_r, goal_c, maze) → float.
    Defaults to Manhattan distance if not provided.
    Any admissible h guarantees an optimal path; inadmissible h finds a
    path faster but may not be shortest.

    The pq_info field in every "step" yield carries a snapshot of the
    top-3 heap entries for the PQ Inspector. h in that snapshot always
    uses whatever heuristic_fn is active so the numbers stay consistent.
    """
    h = heuristic_fn if heuristic_fn is not None else _h_manhattan

    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)
    er, ec     = end

    pq: list[tuple[float, tuple[int, int]]]              = [(0.0, start)]
    parent:     dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    g_score:    dict[tuple[int, int], float]                  = {start: 0.0}
    closed_set: set[tuple[int, int]]                          = set()

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
                    f_score           = new_g + h(nr, nc, er, ec, maze)
                    parent[(nr, nc)]  = curr
                    heapq.heappush(pq, (f_score, (nr, nc)))

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        # PQ Inspector snapshot — top-3 heap entries.
        # h is computed with the active heuristic so the Inspector stays honest.
        # Wrapped in try/except so a buggy plugin doesn't crash the whole run —
        # just blanks the pq_info line for that frame.
        pq_info = ""
        if pq:
            try:
                top   = heapq.nsmallest(min(3, len(pq)), pq)
                parts = []
                for f, (pr, pc) in top:
                    g  = g_score.get((pr, pc), 0)
                    hv = h(pr, pc, er, ec, maze)
                    parts.append(f"({pr},{pc}) g={g:.0f} h={hv:.1f} f={g + hv:.1f}")
                pq_info = "  │  ".join(parts)
            except Exception:
                pq_info = ""   # plugin misbehaved — silent fallback

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