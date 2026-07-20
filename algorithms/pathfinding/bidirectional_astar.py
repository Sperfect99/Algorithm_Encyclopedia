"""
algorithms/pathfinding/bidirectional_astar.py
----------------------------------------------
Bidirectional A* — two simultaneous A* frontiers from S and E.

Generator contract: yields "step" dicts during dual-frontier expansion;
yields "done" when the frontiers collide or queues are exhausted.
"""

from __future__ import annotations

import heapq
import time
from typing import Generator

from core.grid  import DIRECTIONS, PASSABLE, terrain_cost
from core.graph import manhattan_distance
from core.types import RunResult

# Benchmark skip sentinel — PQ Inspector is disabled above this threshold.
_BENCH_SKIP: int = 999_999


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """Bidirectional A* on *maze* (f = g + h, cost-aware).

    Two A* waves expand from S (top-left) and E (bottom-right) simultaneously.
    Each frontier uses Manhattan distance as its heuristic — the forward
    frontier measures distance to E, the backward frontier to S.

    Stopping criterion
    ------------------
    The search terminates when the top of *either* priority queue has
    g >= best_total / 2. This is an MM-inspired approximation rather than
    the full MM rule: it prunes most of the graph and gives good paths
    fast, but the alternating single-step expansion without coordinated
    f-priorities means the meeting node it settles on is occasionally a
    little longer than optimal. The meeting node that minimises
    g_s[m] + g_e[m] among the candidates is chosen.

    Cost vs hop count
    -----------------
    Unlike Bidirectional BFS, g values here accumulate terrain costs
    (mud = 3), so the meeting node minimises actual travel cost.  The
    returned path_cost reflects the true cost including terrain.

    Yields:
        ``{"type": "step", ...}`` for every node expanded on either frontier.
        ``{"type": "done", ...}`` once solved or both queues are exhausted.
    """
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)
    er, ec     = end
    sr, sc     = start

    def h_fwd(r: int, c: int) -> float:
        return float(manhattan_distance((r, c), end))

    def h_bwd(r: int, c: int) -> float:
        return float(manhattan_distance((r, c), start))

    pq_s:     list[tuple[float, tuple[int, int]]]             = [(h_fwd(sr, sc), start)]
    pq_e:     list[tuple[float, tuple[int, int]]]             = [(h_bwd(er, ec), end)]
    g_s:      dict[tuple[int, int], float]                    = {start: 0.0}
    g_e:      dict[tuple[int, int], float]                    = {end:   0.0}
    closed_s: set[tuple[int, int]]                            = set()
    closed_e: set[tuple[int, int]]                            = set()
    parent_s: dict[tuple[int, int], tuple[int, int] | None]   = {start: None}
    parent_e: dict[tuple[int, int], tuple[int, int] | None]   = {end:   None}

    steps        = 0
    compute_time = 0.0
    best_total:  float | None            = None
    candidates:  list[tuple[int, int]]   = []

    if start == end:
        best_total = 0.0
        candidates = [start]
        pq_s.clear()
        pq_e.clear()

    while pq_s or pq_e:
        # ── Advance the forward (start) frontier ─────────────────────────
        if pq_s:
            t0         = time.perf_counter()
            f_s, curr_s = heapq.heappop(pq_s)
            rs, cs     = curr_s

            if curr_s in closed_s:
                compute_time += time.perf_counter() - t0
                continue

            if best_total is not None and g_s.get(curr_s, 0.0) >= best_total / 2:
                pq_s.clear()
                compute_time += time.perf_counter() - t0
            else:
                closed_s.add(curr_s)

                for dr, dc in DIRECTIONS:
                    nr, nc   = rs + dr, cs + dc
                    neighbor = (nr, nc)
                    if (
                        0 <= nr < rows and 0 <= nc < cols
                        and maze[nr][nc] in PASSABLE
                        and neighbor not in closed_s
                    ):
                        new_g = g_s[curr_s] + terrain_cost(maze[nr][nc])
                        if neighbor not in g_s or new_g < g_s[neighbor]:
                            g_s[neighbor]     = new_g
                            parent_s[neighbor] = curr_s
                            heapq.heappush(pq_s, (new_g + h_fwd(nr, nc), neighbor))

                            if neighbor in closed_e:
                                total = new_g + g_e[neighbor]
                                if best_total is None or total < best_total:
                                    best_total = total
                                    candidates = [neighbor]
                                elif total == best_total:
                                    candidates.append(neighbor)

                steps        += 1
                compute_time += time.perf_counter() - t0

                if fog is not None:
                    fog.add((rs, cs))
                if visit_count is not None:
                    visit_count[(rs, cs)] = visit_count.get((rs, cs), 0) + 1

                yield {
                    "type": "step", "r": rs, "c": cs, "steps": steps,
                    "title": "Bidirectional A* ← →", "restore": ".", "pq_info": "",
                    "extra": {"algo": "bidirectional_astar", "frontier": "forward"},
                }

        # ── Advance the backward (end) frontier ──────────────────────────
        if pq_e:
            t0         = time.perf_counter()
            f_e, curr_e = heapq.heappop(pq_e)
            re, ce     = curr_e

            if curr_e in closed_e:
                compute_time += time.perf_counter() - t0
                continue

            if best_total is not None and g_e.get(curr_e, 0.0) >= best_total / 2:
                pq_e.clear()
                compute_time += time.perf_counter() - t0
            else:
                closed_e.add(curr_e)

                for dr, dc in DIRECTIONS:
                    nr, nc   = re + dr, ce + dc
                    neighbor = (nr, nc)
                    if (
                        0 <= nr < rows and 0 <= nc < cols
                        and maze[nr][nc] in PASSABLE
                        and neighbor not in closed_e
                    ):
                        new_g = g_e[curr_e] + terrain_cost(maze[nr][nc])
                        if neighbor not in g_e or new_g < g_e[neighbor]:
                            g_e[neighbor]     = new_g
                            parent_e[neighbor] = curr_e
                            heapq.heappush(pq_e, (new_g + h_bwd(nr, nc), neighbor))

                            if neighbor in closed_s:
                                total = g_s[neighbor] + new_g
                                if best_total is None or total < best_total:
                                    best_total = total
                                    candidates = [neighbor]
                                elif total == best_total:
                                    candidates.append(neighbor)

                steps        += 1
                compute_time += time.perf_counter() - t0

                if fog is not None:
                    fog.add((re, ce))
                if visit_count is not None:
                    visit_count[(re, ce)] = visit_count.get((re, ce), 0) + 1

                yield {
                    "type": "step", "r": re, "c": ce, "steps": steps,
                    "title": "Bidirectional A* ← →", "restore": ".", "pq_info": "",
                    "extra": {"algo": "bidirectional_astar", "frontier": "backward"},
                }

    meeting = min(candidates, key=lambda m: g_s.get(m, 0.0) + g_e.get(m, 0.0)) \
              if candidates else None

    if meeting is None:
        yield {
            "type":    "done",
            "result":  RunResult(float('inf'), compute_time, 0, 0),
            "message": "❌ Bidirectional A*: no path found.",
        }
        return

    # ── Stitch the two parent chains into a single path ──────────────────
    t0 = time.perf_counter()

    path_s: list[tuple[int, int]] = []
    curr: tuple[int, int] | None  = meeting
    while curr is not None:
        path_s.append(curr)
        curr = parent_s.get(curr)
    path_s.reverse()

    path_e: list[tuple[int, int]] = []
    curr = parent_e.get(meeting)
    while curr is not None:
        path_e.append(curr)
        curr = parent_e.get(curr)

    path_len  = 0
    path_cost = 0
    for pr, pc in path_s + path_e:
        if maze[pr][pc] not in {'S', 'E'}:
            path_cost   += terrain_cost(maze[pr][pc])
            maze[pr][pc] = 'P'
            path_len    += 1
            if fog is not None:
                fog.add((pr, pc))

    compute_time += time.perf_counter() - t0
    msg = (
        f"✅ SOLVED! | Steps: {steps} | "
        f"Time: {compute_time * 1000:.2f} ms | "
        f"Path: {path_len} | Cost: {path_cost}"
    )
    yield {
        "type":    "done",
        "result":  RunResult(steps, compute_time, path_len, path_cost),
        "message": msg,
    }
