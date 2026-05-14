"""
algorithms/pathfinding/bfs.py — Breadth-First Search.

Shortest path by hop count. Doesn't care about terrain cost — mud
and road are identical to it.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Generator

from core.grid  import DIRECTIONS, PASSABLE
from core.types import RunResult

from ._shared import reconstruct_path_cells


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """BFS."""
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    queue:   deque[tuple[int, int]]                         = deque([start])
    visited: set[tuple[int, int]]                           = {start}
    parent:  dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    steps        = 0
    compute_time = 0.0

    while queue:
        t0   = time.perf_counter()
        curr = queue.popleft()
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
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < rows and 0 <= nc < cols
                and maze[nr][nc] in PASSABLE
                and (nr, nc) not in visited
            ):
                visited.add((nr, nc))
                parent[(nr, nc)] = curr
                queue.append((nr, nc))

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        yield {"type": "step", "r": r, "c": c, "steps": steps,
               "title": "BFS", "restore": ".", "pq_info": ""}

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ BFS: no path found.",
    }
