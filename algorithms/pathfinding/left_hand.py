"""
algorithms/pathfinding/left_hand.py
-------------------------------------
Left-Hand Rule — mirror of Wall Follower.  O(1) space, memoryless.

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
    Left-Hand Rule on *maze* — keeps the LEFT wall on the agent's left.

    Architecturally identical to Wall Follower but with left-biased turns.
    Same O(1) memory, same failure modes on braided mazes.  May produce
    completely different paths on asymmetric mazes.

    V7 fix (Q-3): detects total enclosure immediately.

    Yields:
        ``{"type": "step", ...}`` for every movement step.
        ``{"type": "done", ...}`` on reaching the exit or failure.
    """
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    # Cardinal directions indexed 0–3: N E S W
    dirs: tuple[tuple[int, int], ...] = ((-1, 0), (0, 1), (1, 0), (0, -1))
    curr_dir          = 2                     # start facing South
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
            msg = (
                f"✅ SOLVED! | Steps: {steps} | "
                f"Time: {compute_time * 1000:.2f} ms | "
                f"Path: {path_len} | Cost: {path_cost}\n"
                f"  📐 Steps = total moves incl. loops; "
                f"Path = loop-free distance ({path_len} ≪ {steps} on winding mazes)"
            )
            yield {
                "type":    "done",
                "result":  RunResult(steps, compute_time, path_len, path_cost),
                "message": msg,
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

        # Left-hand priority: try left → straight → right → back
        # V7 fix (Q-3): detect enclosure with the `moved` flag.
        #
        # ── Compass & turn-offset reference ──────────────────────────────
        # Cardinal directions are indexed:  N=0  E=1  S=2  W=3
        #
        #             N (0)
        #              ↑
        #   W (3) ← [ @ ] → E (1)
        #              ↓
        #             S (2)   ← agent starts here (curr_dir = 2)
        #
        # The turn offsets (-1, 0, 1, 2) applied to curr_dir mod 4 give:
        #   turn = -1  →  (curr_dir - 1) % 4  =  turn LEFT
        #   turn =  0  →  curr_dir             =  go STRAIGHT
        #   turn = +1  →  (curr_dir + 1) % 4  =  turn RIGHT
        #   turn = +2  →  (curr_dir + 2) % 4  =  turn BACK (reverse)
        #
        # Example — agent facing South (curr_dir = 2):
        #   Left   of South  →  (2 - 1) % 4 = 1  →  East   ✓
        #   Straight (South) →  (2 + 0) % 4 = 2  →  South  ✓
        #   Right  of South  →  (2 + 1) % 4 = 3  →  West   ✓
        #   Back   from South→  (2 + 2) % 4 = 0  →  North  ✓
        #
        # "Left of South is East" is initially counter-intuitive: imagine
        # the agent standing at S facing downward (south) — its LEFT hand
        # points east.  The modular arithmetic captures this correctly.
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
               "title": "Left-Hand Rule", "restore": ".", "pq_info": "", "extra": {"algo": "left_hand", "direction": ("N","E","S","W")[curr_dir], "rule": "left-hand"}}

    # unreachable — satisfies type checkers
    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ Left-Hand Rule: unexpected exit.",
    }