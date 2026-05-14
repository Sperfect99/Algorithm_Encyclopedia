"""
algorithms/pathfinding/pledge.py — Pledge Algorithm.

Wall Follower with one extra integer: a cumulative turn counter.
When the counter hits zero again (agent has made a net-zero turn sequence),
it detaches from the current wall and walks freely again. This is what
lets it escape island loops that trap plain Wall Follower.
Still O(1) space — the counter is all that's added.
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
    """Pledge Algorithm."""
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    dirs: tuple[tuple[int, int], ...] = ((-1, 0), (0, 1), (1, 0), (0, -1))
    main_dir          = 2   # preferred direction: South
    curr_dir          = main_dir
    r, c              = start
    steps             = 0
    compute_time      = 0.0
    history: list[tuple[int, int]] = [(r, c)]
    max_allowed_steps = rows * cols * 6
    wall_following    = False
    turn_total        = 0

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
                    f"Path: {path_len} | Cost: {path_cost}"
                ),
            }
            return

        if steps > max_allowed_steps:
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": "❌ Pledge: stuck in a loop (island or braided maze).",
            }
            return

        moved = False

        # ── Free-walk phase: move in main_dir until we hit a wall ──────────
        if not wall_following:
            dr, dc = dirs[main_dir]
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] != 1:
                r, c = nr, nc
                history.append((r, c))
                moved = True
            else:
                wall_following = True
                turn_total     = 0
                curr_dir       = main_dir

        # ── Wall-following phase: right-hand rule + cumulative turn counter ─
        if wall_following and not moved:
            last_turn = 0
            for turn in (1, 0, -1, 2):
                test_dir = (curr_dir + turn) % 4
                dr, dc   = dirs[test_dir]
                nr, nc   = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] != 1:
                    if turn == -1:
                        turn_total -= 1
                    elif turn == 1:
                        turn_total += 1
                    elif turn == 2:
                        turn_total += 2
                    last_turn = turn
                    curr_dir  = test_dir
                    r, c      = nr, nc
                    history.append((r, c))
                    moved     = True
                    break

            if not moved:
                compute_time += time.perf_counter() - t0
                yield {
                    "type":    "done",
                    "result":  RunResult(float('inf'), compute_time, 0, 0),
                    "message": "❌ Pledge: agent completely enclosed by walls.",
                }
                return

            # Detach from wall when turn_total hits zero AND we're facing main_dir.
            # The `last_turn != 0` guard is important: we only detach on an actual
            # turning step, not a straight step. Without it, the agent can detach
            # mid-concavity and oscillate back into the same wall immediately.
            if last_turn != 0 and turn_total == 0 and curr_dir == main_dir:
                wall_following = False

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        yield {
            "type":    "step",
            "r": r, "c": c,
            "steps":   steps,
            "title":   f"Pledge | Compass: {turn_total}",
            "restore": ".",
            "pq_info": "",
        }

    yield {"type": "done", "result": RunResult(float('inf'), compute_time, 0, 0),
           "message": "❌ Pledge: unexpected exit."}
