"""
algorithms/pathfinding/dead_end_filling.py — Dead-End Filling.

Not really a search algorithm — it's a topological operation.
Seals any cell with 3+ wall neighbours, then propagates outward.
What's left after all dead ends are sealed IS the solution path.

Doesn't navigate at all. Doesn't know about terrain cost in any useful way.
Works beautifully on perfect mazes; produces loop remnants on braided ones.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Generator

from core.grid  import DIRECTIONS, terrain_cost
from core.types import RunResult


def _bfs_connected(
    maze:  list[list[int | str]],
    start: tuple[int, int],
    end:   tuple[int, int],
    rows:  int,
    cols:  int,
) -> bool:
    """Check if start can reach end through the surviving (non-wall) cells.

    Called once after the fill phase. Dead-End Filling doesn't guarantee
    connectivity — disconnected components each lose their dead ends
    independently, so we have to verify start actually reaches end.
    """
    visited: set[tuple[int, int]] = {start}
    queue:   deque[tuple[int, int]] = deque([start])
    while queue:
        r, c = queue.popleft()
        if (r, c) == end:
            return True
        for dr, dc in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < rows and 0 <= nc < cols
                and (nr, nc) not in visited
                and maze[nr][nc] != 1
            ):
                visited.add((nr, nc))
                queue.append((nr, nc))
    return False


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """Dead-End Filling."""
    rows, cols   = len(maze), len(maze[0])
    steps        = 0
    compute_time = 0.0

    def _is_wall(r: int, c: int) -> bool:
        if not (0 <= r < rows and 0 <= c < cols):
            return True
        return maze[r][c] == 1

    def _count_walls(r: int, c: int) -> int:
        return sum(1 for dr, dc in DIRECTIONS if _is_wall(r + dr, c + dc))

    # Seed the queue with every cell that already has 3+ wall neighbours
    dead_ends: deque[tuple[int, int]] = deque(
        (r, c)
        for r in range(rows)
        for c in range(cols)
        if maze[r][c] in {0, '.', '~'} and _count_walls(r, c) >= 3
    )
    queued: set[tuple[int, int]] = set(dead_ends)

    # ── Fill phase ────────────────────────────────────────────────────────
    while dead_ends:
        t0   = time.perf_counter()
        r, c = dead_ends.popleft()

        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1
        if fog is not None:
            fog.add((r, c))

        if maze[r][c] in {'S', 'E'}:
            compute_time += time.perf_counter() - t0
            continue

        if _count_walls(r, c) >= 3:
            prev_cell  = maze[r][c]
            maze[r][c] = 1

            compute_time += time.perf_counter() - t0
            steps        += 1

            # Record without rendering — rendering every single cell collapse
            # would be too slow, so we batch renders below
            yield {
                "type": "record_only",
                "r": r, "c": c,
                "prev": prev_cell,
                "new":  1,
                "hud":  f"Running: Dead-End Filling | Walls Collapsed: {steps}",
            }

            if steps % 3 == 0:
                yield {
                    "type":    "render",
                    "steps":   steps,
                    "message": f"Running: Dead-End Filling | Walls Collapsed: {steps}",
                }

            # Check if any neighbours are now newly-dead-ended
            t0 = time.perf_counter()
            for dr, dc in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if (
                    0 <= nr < rows and 0 <= nc < cols
                    and maze[nr][nc] not in {1, 'S', 'E'}
                    and _count_walls(nr, nc) >= 3
                    and (nr, nc) not in queued
                ):
                    dead_ends.append((nr, nc))
                    queued.add((nr, nc))
            compute_time += time.perf_counter() - t0
        else:
            compute_time += time.perf_counter() - t0

    # ── Connectivity check ─────────────────────────────────────────────────
    t0 = time.perf_counter()
    if not _bfs_connected(maze, (0, 0), (rows - 1, cols - 1), rows, cols):
        compute_time += time.perf_counter() - t0
        yield {
            "type":    "done",
            "result":  RunResult(float('inf'), compute_time, 0, 0),
            "message": (
                f"❌ Dead-End Filling: no path found — "
                f"start and end are in disconnected components "
                f"(walls collapsed: {steps})."
            ),
        }
        return

    # ── Reveal surviving solution path ─────────────────────────────────────
    path_len  = 0
    path_cost = 0

    for r in range(rows):
        for c in range(cols):
            if maze[r][c] in {0, '~'}:
                prev_cell  = maze[r][c]
                path_cost += terrain_cost(maze[r][c])
                maze[r][c] = 'P'
                path_len  += 1

                if fog is not None:
                    fog.add((r, c))

                yield {
                    "type": "record_only",
                    "r": r, "c": c,
                    "prev": prev_cell,
                    "new":  'P',
                    "hud":  "Dead-End Filling — solution path revealed",
                }

    compute_time += time.perf_counter() - t0
    path_note = (
        " (includes loop remnants — braided maze)"
        if path_len > (rows + cols) else ""
    )
    yield {
        "type":    "done",
        "result":  RunResult(steps, compute_time, path_len, path_cost),
        "message": (
            f"✅ SOLVED! | Walls Collapsed: {steps} | "
            f"Time: {compute_time * 1000:.2f} ms | "
            f"Surviving cells: {path_len}{path_note} | Cost: {path_cost}"
        ),
    }
