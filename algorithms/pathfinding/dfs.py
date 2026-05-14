"""
algorithms/pathfinding/dfs.py — Depth-First Search.

Plunges deep before backtracking. Finds *a* path, not the best one.
Great for memory efficiency; terrible for path quality.
"""
from __future__ import annotations

import time
from typing import Generator

from core.grid  import DIRECTIONS, PASSABLE
from core.types import RunResult

from ._shared import reconstruct_path_cells


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """DFS."""
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    stack:   list[tuple[int, int]]                          = [start]
    visited: set[tuple[int, int]]                           = {start}
    parent:  dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    steps        = 0
    compute_time = 0.0

    while stack:
        t0   = time.perf_counter()
        curr = stack.pop()
        r, c = curr

        if (r, c) == end:
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
            nr, nc   = r + dr, c + dc
            neighbor = (nr, nc)
            if (
                0 <= nr < rows and 0 <= nc < cols
                and maze[nr][nc] in PASSABLE
                and neighbor not in visited
            ):
                visited.add(neighbor)
                parent[neighbor] = curr
                stack.append(neighbor)

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        yield {"type": "step", "r": r, "c": c, "steps": steps,
               "title": "DFS", "restore": ".", "pq_info": ""}

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ DFS: no path found.",
    }
