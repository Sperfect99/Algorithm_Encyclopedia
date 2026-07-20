"""
algorithms/pathfinding/theta_star.py
--------------------------------------
Theta* — any-angle A* with line-of-sight parent shortcutting.

Generator contract: yields "step" dicts with pq_info for the PQ Inspector;
yields "done" on completion.

Theta* extends A* by checking, for every neighbour, whether a straight
line from the grandparent (the current node's parent) reaches that
neighbour without crossing a wall.  If so, the grandparent is used
directly instead of the current node, allowing paths that cut across
the grid diagonally rather than following the 4-directional grid edges.
"""

from __future__ import annotations

import heapq
import math
import time
from typing import Generator

from core.grid  import DIRECTIONS, PASSABLE, terrain_cost
from core.graph import manhattan_distance
from core.types import RunResult

from ._shared import reconstruct_path_cells

# Benchmark skip sentinel — PQ Inspector is disabled above this threshold.
_BENCH_SKIP: int = 999_999


def _line_of_sight(
    maze: list[list[int | str]],
    r0: int, c0: int,
    r1: int, c1: int,
    rows: int, cols: int,
) -> tuple[bool, float]:
    """Trace a straight line from (r0,c0) to (r1,c1) across the grid.

    Returns (clear, cost). ``clear`` is True when every cell the line
    crosses stays passable; ``cost`` is the terrain cost of the cells
    entered along the way (the origin is not counted, matching how A*
    charges for entering a cell rather than leaving it). When the line
    hits a wall, ``clear`` is False and the cost is meaningless.
    """
    dr = abs(r1 - r0)
    dc = abs(c1 - c0)
    sr = 1 if r1 > r0 else -1
    sc = 1 if c1 > c0 else -1
    err = dr - dc
    r, c = r0, c0
    cost = 0.0

    while True:
        if not (0 <= r < rows and 0 <= c < cols and maze[r][c] in PASSABLE):
            return False, 0.0
        if (r, c) != (r0, c0):
            cost += terrain_cost(maze[r][c])
        if r == r1 and c == c1:
            return True, cost
        e2 = 2 * err
        if e2 > -dc:
            err -= dc
            r   += sr
        if e2 < dr:
            err += dr
            c   += sc


def _euclidean(r0: int, c0: int, r1: int, c1: int) -> float:
    return math.sqrt((r1 - r0) ** 2 + (c1 - c0) ** 2)


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """Theta* on *maze* (any-angle A* with line-of-sight shortcutting).

    For each neighbour of the current node, Theta* checks whether a
    straight line from the current node's parent reaches that neighbour
    without crossing a wall (line-of-sight).  If so, the parent is
    shortcut directly to the neighbour, giving a path that can travel
    at any angle rather than being constrained to grid edges.

    On open mazes this produces noticeably shorter and more natural-looking
    paths than A*.  On dense mazes the LOS check rarely succeeds and the
    behaviour approaches plain A*.

    Terrain (mud) cost is included in the g values.  A line-of-sight
    shortcut charges the geometric distance plus the extra cost of any
    mud the straight line crosses, so cutting across mud is never cheaper
    than the terrain actually warrants.
    """
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)
    er, ec     = end

    def h(r: int, c: int) -> float:
        return float(manhattan_distance((r, c), end))

    pq: list[tuple[float, tuple[int, int]]]                   = [(0.0, start)]
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

        grand = parent.get(curr)   # grandparent — may be None at start

        for dr, dc in DIRECTIONS:
            nr, nc   = r + dr, c + dc
            neighbor = (nr, nc)
            if not (0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] in PASSABLE):
                continue
            if neighbor in closed_set:
                continue

            # ── Theta* line-of-sight check ────────────────────────────────
            # If grandparent has LOS to neighbor, shortcut via grandparent.
            # Otherwise fall back to the standard A* parent assignment.
            los_clear, los_terrain = (False, 0.0)
            if grand is not None:
                los_clear, los_terrain = _line_of_sight(
                    maze, grand[0], grand[1], nr, nc, rows, cols
                )

            if los_clear:
                gr, gc  = grand
                # Geometric (any-angle) distance plus the extra cost of any
                # heavy terrain the straight line crosses, over the base 1/cell.
                span    = _euclidean(gr, gc, nr, nc)
                cells   = max(abs(nr - gr), abs(nc - gc))
                new_g   = g_score[grand] + span + (los_terrain - cells)
                new_par = grand
            else:
                new_g   = g_score[curr] + terrain_cost(maze[nr][nc])
                new_par = curr

            if neighbor not in g_score or new_g < g_score[neighbor]:
                g_score[neighbor] = new_g
                parent[neighbor]  = new_par
                f_score           = new_g + h(nr, nc)
                heapq.heappush(pq, (f_score, neighbor))

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        pq_info = ""
        if pq:
            top   = heapq.nsmallest(min(3, len(pq)), pq)
            parts = []
            for f, (pr, pc) in top:
                g  = g_score.get((pr, pc), 0)
                hv = h(pr, pc)
                parts.append(f"({pr},{pc}) g={g:.1f} h={hv:.0f} f={g + hv:.1f}")
            pq_info = "  │  ".join(parts)

        _h_val = h(r, c)
        yield {
            "type":    "step",
            "r": r, "c": c,
            "steps":   steps,
            "title":   "Theta* (Any-Angle)",
            "restore": ".",
            "pq_info": pq_info,
            "extra": {
                "algo":        "theta_star",
                "g":           g_score.get(curr, 0),
                "h":           _h_val,
                "f":           g_score.get(curr, 0) + _h_val,
                "open_size":   len(pq),
                "closed_size": len(closed_set),
            },
        }

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ Theta*: no path found.",
    }
