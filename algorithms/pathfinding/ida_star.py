"""
algorithms/pathfinding/ida_star.py
-----------------------------------
IDA* — Iterative Deepening A*.  Space: O(depth).

Generator contract: yields "step" dicts for every node touched (including
re-expansions); yields "done" on completion or when bound exceeds any path.
"""

from __future__ import annotations

import time
from typing import Generator

from core.grid  import DIRECTIONS, PASSABLE, terrain_cost
from core.graph import manhattan_distance
from core.types import RunResult

from ._shared import reconstruct_path_cells


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """
    IDA* on *maze* — iterative-deepening A* with an explicit stack.

    Runs bounded DFS iterations with increasing f-score thresholds.
    Stores only the current path — O(d) space, where d is the solution
    depth.  The ``steps`` counter includes all re-expansions, showing the
    explicit memory-vs-time tradeoff.

    Uses an explicit stack of frames (not Python recursion) to avoid
    hitting the interpreter's recursion limit on deep mazes.

    Yields:
        ``{"type": "step", ...}`` for every node first entered in each bound.
        ``{"type": "done", ...}`` once solved or all bounds exhausted.
    """
    rows, cols  = len(maze), len(maze[0])
    start, end  = (0, 0), (rows - 1, cols - 1)
    threshold   = float(manhattan_distance(start, end))
    n_iters     = 0

    # Dynamic iteration ceiling — replaces the hard-coded 300.
    #
    # Why 300 was wrong: IDA* advances its f-bound to the smallest value
    # that exceeded the previous bound.  On a weighted grid (mud cost = 3,
    # road cost = 1) each step raises the f-score by between 1 and 3.  The
    # number of distinct thresholds from the initial Manhattan distance to
    # the true optimal cost is therefore bounded by:
    #
    #     max_thresholds ≤ optimal_cost ≤ rows * cols * max_terrain_cost
    #                                    = rows * cols * 3
    #
    # For a 61×151 maze that is ≈ 27 000 — far beyond 300.  In practice
    # thresholds advance in larger steps, but the cliff was invisible.
    #
    # We set the ceiling to (rows * cols * 3) — a tight mathematical upper
    # bound.  Early-termination via `min_exceeded == inf` (line below) fires
    # long before this ceiling on any solvable maze; the ceiling is only hit
    # when IDA* is processing an unsolvable or astronomically expensive map.
    # The message distinguishes "iteration cap hit" from "truly no path".
    MAX_ITERS   = rows * cols * 3

    steps        = 0
    compute_time = 0.0

    for _ in range(MAX_ITERS):
        # Each frame: [position, g_cost, neighbours_list, neighbour_idx, entered]
        path_set: set[tuple[int, int]]                           = {start}
        parent:   dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        frames:   list[list] = [[start, 0.0, None, 0, False]]
        min_exceeded = float('inf')
        found        = False

        while frames:
            frame                           = frames[-1]
            pos, g, neighbours, idx, entered = frame
            r, c = pos

            if not entered:
                frame[4] = True
                h        = float(manhattan_distance(pos, end))
                f        = g + h

                if f > threshold:
                    if f < min_exceeded:
                        min_exceeded = f
                    frames.pop()
                    path_set.discard(pos)
                    continue

                # M-10 fix: the timing block must encompass the actual
                # computation — neighbor generation and f-score evaluation.
                # The original block only contained `steps += 1` (a single
                # integer increment), making compute_time ≈ 0 ns for every
                # run and the profiling metric completely meaningless.
                t0     = time.perf_counter()
                steps += 1

                if pos == end:
                    compute_time += time.perf_counter() - t0
                    found = True
                    break

                # Generate neighbors — this is the dominant per-node cost.
                frame[2] = [
                    (r + dr, c + dc)
                    for dr, dc in DIRECTIONS
                    if (
                        0 <= r + dr < rows and 0 <= c + dc < cols
                        and maze[r + dr][c + dc] in PASSABLE
                    )
                ]
                neighbours    = frame[2]
                compute_time += time.perf_counter() - t0

                if fog is not None:
                    fog.add(pos)
                if visit_count is not None:
                    visit_count[pos] = visit_count.get(pos, 0) + 1

                yield {
                    "type":    "step",
                    "r": r, "c": c,
                    "steps":   steps,
                    "title":   f"IDA* | Threshold: {threshold:.0f}",
                    "restore": ".",
                    "pq_info": "",
                    "extra": {"algo": "ida_star", "depth": g, "bound": threshold},
                }

            while idx < len(neighbours):
                nbr  = neighbours[idx]
                idx += 1
                frame[3] = idx

                if nbr not in path_set:
                    nr2, nc2    = nbr
                    new_g       = g + terrain_cost(maze[nr2][nc2])
                    parent[nbr] = pos
                    path_set.add(nbr)
                    frames.append([nbr, new_g, None, 0, False])
                    break
            else:
                frames.pop()
                path_set.discard(pos)

        if found:
            t1 = time.perf_counter()
            path_len, path_cost = reconstruct_path_cells(parent, end, maze, fog)
            pure_time = compute_time + (time.perf_counter() - t1)
            msg = (
                f"✅ SOLVED! | Steps: {int(steps)} | "
                f"Threshold iterations: {n_iters} | "
                f"Final bound: {threshold:.0f} | "
                f"Time: {pure_time * 1000:.2f} ms | "
                f"Path: {path_len} | Cost: {path_cost}"
            )
            yield {
                "type":    "done",
                "result":  RunResult(steps, pure_time, path_len, path_cost),
                "message": msg,
            }
            return

        if min_exceeded == float('inf'):
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": "❌ IDA*: no path found.",
            }
            return

        threshold = min_exceeded
        n_iters  += 1

    # Reached MAX_ITERS without finding a solution or proving infeasibility.
    # On a connected maze this should be mathematically impossible with the
    # dynamic ceiling — if it fires, report enough context for diagnosis.
    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": (
            f"❌ IDA*: hit search limit ({MAX_ITERS} iterations). "
            f"Last f-threshold: {threshold:.0f}. "
            f"This does not mean the maze is unsolvable — "
            f"run BFS or A* to check. Likely cause: heavy mud terrain "
            f"inflating path cost beyond the iteration budget."
        ),
    }