"""
algorithms/pathfinding/dead_end_filling.py
--------------------------------------------
Dead-End Filling — topological, not navigational.

Generator contract: yields "record_only" dicts as cells are walled up
(autopsy capture without rendering), and "render" dicts at frame
intervals.  Yields "done" once the solution path is revealed.

This algorithm is unique: it modifies the maze in-place by sealing dead
ends (setting them to ``1``) rather than moving through it.
"""

from __future__ import annotations

import time
from collections import deque
from typing      import Generator

from core.grid  import DIRECTIONS, terrain_cost
from core.types import RunResult

# ---------------------------------------------------------------------------
# Module-level BFS used exclusively for the post-fill connectivity check.
# Kept inline (not imported from core.graph) because this is the only
# call site and adding a public function to graph.py for one algorithm
# would widen that module's interface unnecessarily.
# ---------------------------------------------------------------------------
def _bfs_connected(
    maze:  list[list[int | str]],
    start: tuple[int, int],
    end:   tuple[int, int],
    rows:  int,
    cols:  int,
) -> bool:
    """Return True if *start* can reach *end* through surviving passable cells.

    'Surviving' means any cell whose value is NOT ``1`` — i.e. the cells
    that dead-end filling left standing, including ``'S'``, ``'E'``, ``0``,
    and ``'~'``.  Called once after the fill phase to verify global
    connectivity before claiming a solution.
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
    """
    Dead-End Filling on *maze*.

    Iteratively seals cells that have ≥ 3 wall neighbours.  Continues
    until only the solution path (and special cells) remain.  Topological:
    never navigates — eliminates all dead ends.

    The ``"record_only"`` yields allow the animator's autopsy recorder
    to capture every individual cell-to-wall mutation without triggering
    a visual render on every step (which would be extremely slow).

    Yields:
        ``{"type": "record_only", ...}`` for every cell sealed (wall collapse).
        ``{"type": "render", ...}``      every ``_FRAME_INTERVAL`` collapses.
        ``{"type": "record_only", ...}`` for every path cell revealed.
        ``{"type": "done", ...}``        once the solution is fully marked.
    """
    rows, cols   = len(maze), len(maze[0])
    steps        = 0
    compute_time = 0.0
    sealed       = 0

    # ── Local wall-check helpers ──────────────────────────────────────────
    def _is_wall(r: int, c: int) -> bool:
        if not (0 <= r < rows and 0 <= c < cols):
            return True
        return maze[r][c] == 1

    def _count_walls(r: int, c: int) -> int:
        return sum(1 for dr, dc in DIRECTIONS if _is_wall(r + dr, c + dc))

    # ── Seed the dead-end queue ───────────────────────────────────────────
    dead_ends: deque[tuple[int, int]] = deque(
        (r, c)
        for r in range(rows)
        for c in range(cols)
        if maze[r][c] in {0, '.', '~'} and _count_walls(r, c) >= 3
    )
    queued: set[tuple[int, int]] = set(dead_ends)

    # ── Fill dead ends ────────────────────────────────────────────────────
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

            # Record the wall-collapse for autopsy (no render)
            sealed += 1
            yield {
                "type": "record_only",
                "r":    r,
                "c":    c,
                "extra": {"algo": "dead_end", "sealed": sealed},
                "prev": prev_cell,
                "new":  1,
                "hud":  f"Running: Dead-End Filling | Walls Collapsed: {steps}",
            }

            # Periodically emit a render frame
            if steps % 3 == 0:
                yield {
                    "type":    "render",
                    "steps":   steps,
                    "message": f"Running: Dead-End Filling | Walls Collapsed: {steps}",
                }

            # Propagate: any newly-created dead ends?
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

    # ── Connectivity check ────────────────────────────────────────────────
    # Dead-End Filling guarantees that every DEAD END is removed, but it
    # does NOT guarantee that the surviving corridor connects start to end.
    # On a maze with two disconnected components, both components lose their
    # dead ends independently and the remaining corridors declare "solved"
    # with no actual path from S to E.  We must verify connectivity first.
    t0 = time.perf_counter()
    start_cell = (0, 0)
    end_cell   = (rows - 1, cols - 1)

    if not _bfs_connected(maze, start_cell, end_cell, rows, cols):
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

    # ── Reveal the surviving solution path ───────────────────────────────
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

                # Record the path-reveal for autopsy
                yield {
                    "type": "record_only",
                    "r":    r,
                    "c":    c,
                    "prev": prev_cell,
                    "new":  'P',
                    "hud":  "Dead-End Filling — solution path revealed",
                }

    compute_time += time.perf_counter() - t0
    path_note = (
        " (includes loop remnants — braided maze)"
        if path_len > (rows + cols) else ""
    )
    msg = (
        f"✅ SOLVED! | Walls Collapsed: {steps} | "
        f"Time: {compute_time * 1000:.2f} ms | "
        f"Surviving cells: {path_len}{path_note} | Cost: {path_cost}"
    )
    yield {
        "type":    "done",
        "result":  RunResult(steps, compute_time, path_len, path_cost),
        "message": msg,
    }