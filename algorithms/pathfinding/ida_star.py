"""
algorithms/pathfinding/ida_star.py — IDA* (Iterative Deepening A*).

A* with O(depth) space instead of O(V). Repeatedly runs bounded DFS
with increasing f-score thresholds until the goal is found. Re-expands
nodes across iterations, which is why the step count looks high — it's
trading memory for computation.

Uses an explicit stack (not Python recursion) to avoid hitting the
recursion limit on large mazes.
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
    """IDA*."""
    rows, cols  = len(maze), len(maze[0])
    start, end  = (0, 0), (rows - 1, cols - 1)
    threshold   = float(manhattan_distance(start, end))
    n_iters     = 0

    # ceil = rows*cols*3 covers all possible f-score thresholds on a weighted grid.
    # In practice min_exceeded == inf exits long before we hit this.
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

                # Timing must cover neighbour generation — that's most of the work
                t0     = time.perf_counter()
                steps += 1

                if pos == end:
                    compute_time += time.perf_counter() - t0
                    found = True
                    break

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
            yield {
                "type":    "done",
                "result":  RunResult(steps, pure_time, path_len, path_cost),
                "message": (
                    f"✅ SOLVED! | Steps: {int(steps)} | "
                    f"Threshold iterations: {n_iters} | "
                    f"Final bound: {threshold:.0f} | "
                    f"Time: {pure_time * 1000:.2f} ms | "
                    f"Path: {path_len} | Cost: {path_cost}"
                ),
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

    # Only reachable on unsolvable or astronomically expensive mazes
    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": (
            f"❌ IDA*: iteration ceiling reached ({MAX_ITERS} bounds). "
            f"Last threshold: {threshold:.0f}. "
            f"This maze likely has extremely high terrain cost or is "
            f"unsolvable — verify with BFS/A*."
        ),
    }
