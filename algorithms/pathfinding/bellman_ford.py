"""
algorithms/pathfinding/bellman_ford.py — Bellman-Ford.

Relaxes all edges repeatedly until no improvement is found.
Cost-aware and handles any non-negative weights. Correct on this grid.
Slower than Dijkstra on sparse graphs (O(V·E) vs O((V+E)logV)) but a
classic teaching algorithm — and the only one here that processes ALL edges
every pass rather than expanding one node at a time.

Yields one "render" frame per pass (not per edge) so you can watch
the wavefront grow across the maze.
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
    """Bellman-Ford."""
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

    # Build the full edge list once — O(V) time, then reuse every pass
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

    # V-1 passes is the theoretical max for a diameter-V-1 snake maze.
    # Early exit when nothing updated means we're usually done way before this.
    max_passes   = total_cells - 1
    reached:      set[tuple[int, int]] = {start}
    prev_reached: set[tuple[int, int]] = set()
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
                relaxations += 1
                reached.add(v)
                if visit_count is not None:
                    visit_count[v] = visit_count.get(v, 0) + 1
                if fog is not None:
                    fog.add(v)

        passes       += 1
        compute_time += time.perf_counter() - t0

        # emit record_only for each newly reached cell so autopsy can replay it
        newly_reached = reached - prev_reached
        for nr, nc in sorted(newly_reached):
            if maze[nr][nc] not in {'S', 'E'}:
                yield {
                    "type": "record_only",
                    "r": nr, "c": nc,
                    "prev": maze[nr][nc],
                    "new":  '.',
                    "hud": (
                        f"Running: Bellman-Ford | Pass {passes} | "
                        f"Relaxations: {relaxations} | Reached: {len(reached)}"
                    ),
                }
        prev_reached = set(reached)

        # Temporarily stamp reached cells '.' for the render frame, then restore
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
    yield {
        "type":    "done",
        "result":  RunResult(relaxations, pure_time, path_len, path_cost),
        "message": (
            f"✅ SOLVED! | Relaxations: {relaxations} | Passes: {passes} | "
            f"Time: {pure_time * 1000:.2f} ms | "
            f"Path: {path_len} | Cost: {path_cost}"
        ),
    }
