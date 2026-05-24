"""
algorithms/pathfinding/dfs.py
------------------------------
Depth-First Search — LIFO, non-optimal.

Generator contract: yields "step" dicts during exploration;
yields "done" when solved or stack exhausted.
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
    """
    Depth-First Search on *maze*.

    Explores neighbours in LIFO order — finds a path (not necessarily the
    best).  Highly memory-efficient; path quality varies by maze structure.

    Yields:
        ``{"type": "step", ...}`` for every node expanded.
        ``{"type": "done", ...}`` once solved or stack exhausted.
    """
    rows, cols        = len(maze), len(maze[0])
    start: tuple[int, int] = (0, 0)
    end:   tuple[int, int] = (rows - 1, cols - 1)

    stack:   list[tuple[int, int]]                           = [start]
    visited: set[tuple[int, int]]                            = {start}
    parent:  dict[tuple[int, int], tuple[int, int] | None]  = {start: None}

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

        # Neighbor generation is the dominant per-node cost — it must be
        # inside the timed block.  Previously the loop sat after
        # `compute_time += ...`, so every DFS expansion recorded only the
        # pop + goal-check cost while the four hash-set lookups and stack
        # appends were attributed to zero time, understating compute_time
        # by roughly 5× and making DFS appear artificially faster than
        # A*/Dijkstra in benchmark comparisons.
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

        yield {"type": "step", "r": r, "c": c, "steps": steps, "title": "DFS",
               "restore": ".", "pq_info": "", "extra": {"algo": "dfs", "stack_size": len(stack)}}

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ DFS: no path found.",
    }