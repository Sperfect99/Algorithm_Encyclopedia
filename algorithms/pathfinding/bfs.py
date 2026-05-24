"""
algorithms/pathfinding/bfs.py
------------------------------
Breadth-First Search — hop-optimal, cost-blind.

Generator contract: yields "step" dicts during exploration;
yields "done" when solved or when the queue is exhausted.
"""

from __future__ import annotations

import time
from collections import deque
from typing      import Generator

from core.grid  import DIRECTIONS, PASSABLE
from core.types import RunResult

from ._shared import reconstruct_path_cells


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """
    Breadth-First Search on *maze*.

    Explores neighbours in FIFO order — guarantees the fewest-hop path.
    Cost-blind: mud terrain is treated identically to road.

    Yields:
        ``{"type": "step", ...}`` for every node expanded.
        ``{"type": "done", ...}`` once solved or queue exhausted.
    """
    rows, cols        = len(maze), len(maze[0])
    start: tuple[int, int] = (0, 0)
    end:   tuple[int, int] = (rows - 1, cols - 1)

    queue:   deque[tuple[int, int]]                          = deque([start])
    visited: set[tuple[int, int]]                            = {start}
    parent:  dict[tuple[int, int], tuple[int, int] | None]  = {start: None}
    dist:    dict[tuple[int, int], int]                      = {start: 0}

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
            msg = (
                f"✅ SOLVED! | Steps: {int(steps)} | "
                f"Time: {pure_time * 1000:.2f} ms | "
                f"Path: {path_len} | Cost: {path_cost}"
            )
            yield {
                "type":   "done",
                "result": RunResult(steps, pure_time, path_len, path_cost),
                "message": msg,
            }
            return

        # Neighbor generation is the dominant per-node cost — it must be
        # inside the timed block.  Previously the loop sat after
        # `compute_time += ...`, so every BFS expansion recorded only the
        # dequeue + goal-check cost (~20 ns) while the four hash-set lookups
        # and queue appends (~100 ns each) were attributed to zero time.
        # On a 25×51 maze that understated compute_time by roughly 5×.
        for dr, dc in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < rows and 0 <= nc < cols
                and maze[nr][nc] in PASSABLE
                and (nr, nc) not in visited
            ):
                visited.add((nr, nc))
                parent[(nr, nc)]  = curr
                dist[(nr, nc)]    = dist.get(curr, 0) + 1
                queue.append((nr, nc))

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        yield {"type": "step", "r": r, "c": c, "steps": steps, "title": "BFS",
               "restore": ".", "pq_info": "",
               "extra": {"algo": "bfs", "dist": dist.get((r, c), 0), "queue_size": len(queue)}}

    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ BFS: no path found.",
    }