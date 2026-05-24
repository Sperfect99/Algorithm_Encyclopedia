"""
algorithms/pathfinding/pledge.py
----------------------------------
Pledge Algorithm — escapes wall islands.  O(1) space.

Generator contract: yields "step" dicts as the agent walks;
yields "done" on solution or failure.
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
    """
    Pledge Algorithm on *maze*.

    Adds ONE cumulative turn integer to Wall Follower.  When the counter
    returns to zero and the agent faces the main direction again, wall-
    following is suspended — detaching from island loops that trap plain
    Wall Follower.  Still O(1) space.

    V7 fix (A-3): yields a ``"done"`` failure frame on timeout instead of
    returning silently, so the last animation frame always shows a message.

    Yields:
        ``{"type": "step", ..., "title": "Pledge | Compass: N"}`` per step.
        ``{"type": "done", ...}`` on reaching the exit or failure.
    """
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    # Cardinal directions indexed 0–3: N E S W
    dirs: tuple[tuple[int, int], ...] = ((-1, 0), (0, 1), (1, 0), (0, -1))
    main_dir          = 2             # preferred direction: South
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
            msg = (
                f"✅ SOLVED! | Steps: {steps} | "
                f"Time: {compute_time * 1000:.2f} ms | "
                f"Path: {path_len} | Cost: {path_cost}"
            )
            yield {
                "type":    "done",
                "result":  RunResult(steps, compute_time, path_len, path_cost),
                "message": msg,
            }
            return

        if steps > max_allowed_steps:
            compute_time += time.perf_counter() - t0
            # V7 fix (A-3): emit a visible failure message
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": "❌ Pledge: stuck in a loop (island or braided maze).",
            }
            return

        moved = False

        # ── Free-walk phase: move in main_dir until a wall ──────────────
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

        # ── Wall-following phase: right-hand rule with turn counter ─────
        if wall_following and not moved:
            last_turn = 0   # records the turn offset used for this step
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

            # C-5 fix: enclosure guard — all four neighbors are walls.
            # Without this, `moved` stays False and the agent yields from
            # the same cell until the step limit, wasting the entire budget.
            if not moved:
                compute_time += time.perf_counter() - t0
                yield {
                    "type":    "done",
                    "result":  RunResult(float('inf'), compute_time, 0, 0),
                    "message": "❌ Pledge: agent completely enclosed by walls.",
                }
                return

            # Detach from wall when the cumulative turn counter returns to
            # zero AND the agent is facing main_dir again.
            #
            # Canonical Pledge invariant: detachment must be triggered by an
            # actual TURNING step (last_turn != 0), not a straight step
            # (last_turn == 0).
            #
            # Why this matters on concave obstacles:
            #   A straight step (turn == 0) never changes turn_total.  If
            #   turn_total is already 0 and curr_dir == main_dir before a
            #   straight step, those facts remain true after it — but the
            #   agent has not completed any net-zero turn sequence; it simply
            #   walked forward.  Detaching here while still inside a concave
            #   recess causes the agent to immediately re-hit the inner wall,
            #   re-enter wall-following at turn_total=0, and oscillate until
            #   the step budget is exhausted.
            #
            #   With `last_turn != 0`, detachment only fires when the step
            #   that zeroed the counter was itself a left-turn — i.e., the
            #   agent has genuinely completed a topological loop around an
            #   obstacle feature and is now clear to continue straight.
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
            "extra": {"algo": "pledge",
                      "direction": ("N","E","S","W")[curr_dir % 4],
                      "turn_count": turn_total},
        }

    # unreachable — satisfies type checkers
    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ Pledge: unexpected exit.",
    }