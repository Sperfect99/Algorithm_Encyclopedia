"""
algorithms/pathfinding/bellman_ford.py
---------------------------------------
Bellman-Ford — edge-relaxation, O(V·E).

Generator contract: yields "step" dicts once per relaxation pass (not per
edge), with the current reached-set already temporarily applied to the maze
for rendering.  The "render" yield type is used here because the pass-level
render is fundamentally different from single-node expansion.
"""

from __future__ import annotations

import time
from typing import Generator

from core.grid  import DIRECTIONS, terrain_cost
from core.types import RunResult

from ._shared import reconstruct_path_cells


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """
    Bellman-Ford on *maze* — relaxes all edges each pass.

    Cost-aware: handles any non-negative weights (mud = 3, road = 1).
    Converges in O(diameter) passes with early termination when no
    distances are updated.

    Yields one ``"render"`` dict per relaxation pass for the animator to
    display.  The maze is temporarily modified (reached cells marked ``'.'``)
    when the yield occurs, and restored immediately after the yield returns.

    NOTE: The large-maze warning (> 2 500 cells) is handled by the controller
    *before* calling ``solve()``, so this generator never blocks on input.

    Yields:
        ``{"type": "render", ...}`` once per relaxation pass.
        ``{"type": "done", ...}`` once solved or all passes exhausted.
    """
    rows, cols  = len(maze), len(maze[0])
    start, end  = (0, 0), (rows - 1, cols - 1)
    total_cells = rows * cols
    INF         = float('inf')

    dist:   dict[tuple[int, int], float]                  = {}
    parent: dict[tuple[int, int], tuple[int, int] | None] = {}

    for r in range(rows):
        for c in range(cols):
            if maze[r][c] != 1:
                dist[(r, c)]   = INF
                parent[(r, c)] = None
    dist[start] = 0.0

    # Build full edge list once — O(V) time
    edges: list[tuple[tuple[int, int], tuple[int, int], int]] = []
    for r in range(rows):
        for c in range(cols):
            if maze[r][c] == 1:
                continue
            u = (r, c)
            for dr, dc in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] != 1:
                    edges.append((u, (nr, nc), terrain_cost(maze[nr][nc])))

    # The correct Bellman-Ford bound is (V − 1) passes.  A grid maze can
    # have a diameter up to (rows * cols − 1) hops in a snake configuration,
    # so capping below that value causes non-convergence on large mazes.
    # The `if not updated: break` early-exit below keeps typical runtimes
    # well under this theoretical ceiling — no artificial cap is needed.
    max_passes   = total_cells - 1
    reached:     set[tuple[int, int]] = {start}
    prev_reached: set[tuple[int, int]] = set()   # M-6: track wavefront growth
    # M-8 fix: `relaxations` counts individual edge updates — a unit of
    # work comparable to "nodes expanded" in BFS/A*/Dijkstra.  Previously
    # `steps` counted relaxation PASSES (≤ total_cells − 1), which made
    # Bellman-Ford appear vastly cheaper than it is in benchmark tables.
    relaxations  = 0
    passes       = 0
    compute_time = 0.0

    for pass_num in range(max_passes):
        t0      = time.perf_counter()
        updated = False

        for u, v, cost in edges:
            if dist[u] != INF and dist[u] + cost < dist[v]:
                dist[v]      = dist[u] + cost
                parent[v]    = u
                updated      = True
                relaxations += 1          # one edge relaxation = one unit of work
                reached.add(v)
                if visit_count is not None:
                    visit_count[v] = visit_count.get(v, 0) + 1
                if fog is not None:
                    fog.add(v)

        passes       += 1
        compute_time += time.perf_counter() - t0

        # M-6 fix: emit "record_only" events for every cell newly added to
        # the wavefront this pass so the autopsy replayer can reconstruct
        # Bellman-Ford's progressive exploration.  Previously, "render"
        # yields were never appended to active_recording, making B-F the
        # only algorithm that produced an empty autopsy replay.
        newly_reached = reached - prev_reached
        for nr, nc in sorted(newly_reached):   # sorted for deterministic replay
            if maze[nr][nc] not in {'S', 'E'}:
                yield {
                    "type": "record_only",
                    "r":    nr,
                    "c":    nc,
                    "prev": maze[nr][nc],
                    "new":  '.',
                    "hud":  (
                        f"Running: Bellman-Ford | Pass {passes} | "
                        f"Relaxations: {relaxations} | Reached: {len(reached)}"
                    ),
                    "extra": {"algo": "bellman_ford", "round": passes},
                }
        prev_reached = set(reached)

        # Temporarily mark reached cells '.' for the render frame, then restore.
        saved: dict[tuple[int, int], int | str] = {}
        for mr, mc in reached:
            if maze[mr][mc] not in {'S', 'E'}:
                saved[(mr, mc)] = maze[mr][mc]
                maze[mr][mc]    = '.'

        yield {
            "type":    "render",
            "steps":   relaxations,
            "message": (
                f"Running: Bellman-Ford | Pass {passes} | "
                f"Relaxations: {relaxations} | Reached: {len(reached)}"
            ),
        }

        # Restore after the animator has rendered
        for (mr, mc), val in saved.items():
            maze[mr][mc] = val

        if not updated:
            break

    if dist[end] == INF:
        yield {
            "type":    "done",
            "result":  RunResult(float('inf'), compute_time, 0, 0),
            "message": "❌ Bellman-Ford: no path found.",
        }
        return

    t1 = time.perf_counter()
    path_len, path_cost = reconstruct_path_cells(parent, end, maze, fog)
    pure_time = compute_time + (time.perf_counter() - t1)
    msg = (
        f"✅ SOLVED! | Relaxations: {relaxations} | Passes: {passes} | "
        f"Time: {pure_time * 1000:.2f} ms | "
        f"Path: {path_len} | Cost: {path_cost}"
    )
    yield {
        "type":    "done",
        "result":  RunResult(relaxations, pure_time, path_len, path_cost),
        "message": msg,
    }