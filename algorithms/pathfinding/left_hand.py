"""
algorithms/pathfinding/left_hand.py — Left-Hand Rule.

Mirror image of Wall Follower: keep your LEFT hand on the wall instead.
Same O(1) space, same failure modes on braided mazes. Often produces a
completely different path on asymmetric mazes, which is the whole point
of having both — to show that left and right are architecturally equivalent.
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
    """Left-Hand Rule."""
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
                "message": "❌ Left-Hand Rule: stuck in an infinite loop.",
            }
            return

        # Left-hand priority: try left → straight → right → back.
        # Turn offsets applied to curr_dir mod 4:
        #   -1 = turn left, 0 = straight, +1 = turn right, +2 = reverse
        #
        # "Left of South is East" seems backwards — but imagine standing
        # at position S facing downward. Your left hand points east. ✓
        moved = False
        for turn in (-1, 0, 1, 2):
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
                "message": "❌ Left-Hand Rule: completely enclosed — no valid move.",
            }
            return

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        yield {"type": "step", "r": r, "c": c, "steps": steps,
               "title": "Left-Hand Rule", "restore": ".", "pq_info": ""}

    yield {"type": "done", "result": RunResult(float('inf'), compute_time, 0, 0),
           "message": "❌ Left-Hand Rule: unexpected exit."}
