"""
algorithms/pathfinding/wall_follower.py — Wall Follower (Right-Hand Rule).

Keep your right hand on the wall. That's the whole algorithm.
O(1) space — it only knows current position and heading. No cost model.
Fails spectacularly on mazes with disconnected wall islands (complexity >= 5).
"""
from __future__ import annotations

import time
from typing import Generator

from core.grid  import terrain_cost
from core.types import RunResult

from ._shared import wall_follower_path_cells


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """Wall Follower (right-hand rule)."""
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    # Cardinal directions: N=0, E=1, S=2, W=3
    dirs: tuple[tuple[int, int], ...] = ((-1, 0), (0, 1), (1, 0), (0, -1))
    curr_dir          = 2   # start facing South
    r, c              = start
    steps             = 0
    compute_time      = 0.0
    history: list[tuple[int, int]] = [(r, c)]
    max_allowed_steps = rows * cols * 4

    while True:
        t0 = time.perf_counter()

        if (r, c) == end:
            path_len, path_cost = wall_follower_path_cells(history, maze, fog)
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(steps, compute_time, path_len, path_cost),
                "message": (
                    f"✅ SOLVED! | Steps: {steps} | "
                    f"Time: {compute_time * 1000:.2f} ms | "
                    f"Path: {path_len} | Cost: {path_cost}\n"
                    f"  📐 Steps = total moves incl. loops; "
                    f"Path = loop-free distance ({path_len} ≪ {steps} on winding mazes)"
                ),
            }
            return

        if steps > max_allowed_steps:
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": "❌ Wall Follower: stuck in an infinite loop.",
            }
            return

        # Right-hand priority: try right → straight → left → back.
        # The `moved` flag catches complete enclosure — all 4 neighbours are walls.
        # Without it the agent spins on the same cell until it hits max_allowed_steps,
        # which on a large slow maze could take hours.
        moved = False
        for turn in (1, 0, -1, 2):
            test_dir = (curr_dir + turn) % 4
            dr, dc   = dirs[test_dir]
            nr, nc   = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] != 1:
                r, c     = nr, nc
                curr_dir = test_dir
                history.append((r, c))
                moved    = True
                break

        if not moved:
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": "❌ Wall Follower: completely enclosed — no valid move.",
            }
            return

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        yield {"type": "step", "r": r, "c": c, "steps": steps,
               "title": "Wall Follower (Right-Hand)", "restore": ".", "pq_info": ""}

    # unreachable — keeps type checkers happy
    yield {"type": "done", "result": RunResult(float('inf'), compute_time, 0, 0),
           "message": "❌ Wall Follower: unexpected exit."}
