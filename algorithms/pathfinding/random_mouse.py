"""
algorithms/pathfinding/random_mouse.py
----------------------------------------
Random Mouse — Drunkard's Walk.  Cap: 10 000 steps.

Generator contract: yields "step" dicts as the agent wanders;
yields "done" on solution, cap, or isolation.
"""

from __future__ import annotations

import random
import time
from typing import Generator

from core.grid  import DIRECTIONS, terrain_cost
from core.types import RunResult

from ._shared import wall_follower_path_cells


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """
    Random Mouse (Drunkard's Walk) on *maze*.

    Chooses a random valid neighbour at each step — no memory, no
    heuristic, no cost model.  Capped at 10 000 steps.

    V7 fix (Q-2): guards against a completely enclosed cell (raises no
    IndexError on an empty ``valid_moves`` list; returns failure cleanly).

    Yields:
        ``{"type": "step", ...}`` per wandering step.
        ``{"type": "done", ...}`` on exit, cap exceeded, or isolation.
    """
    rows, cols = len(maze), len(maze[0])
    r, c       = 0, 0
    end        = (rows - 1, cols - 1)

    steps        = 0
    compute_time = 0.0
    history: list[tuple[int, int]] = [(r, c)]
    max_steps    = 10_000

    while True:
        t0 = time.perf_counter()

        if (r, c) == end:
            path_len, path_cost = wall_follower_path_cells(history, maze, fog)
            compute_time += time.perf_counter() - t0
            msg = (
                f"✅ SOLVED! (Pure Luck) | Steps: {steps} | "
                f"Time: {compute_time * 1000:.2f} ms | "
                f"Path: {path_len} | Cost: {path_cost}"
            )
            yield {
                "type":    "done",
                "result":  RunResult(steps, compute_time, path_len, path_cost),
                "message": msg,
            }
            return

        if steps >= max_steps:
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": f"❌ Random Mouse gave up after {max_steps} steps.",
            }
            return

        valid_moves = [
            (r + dr, c + dc)
            for dr, dc in DIRECTIONS
            if 0 <= r + dr < rows and 0 <= c + dc < cols
            and maze[r + dr][c + dc] != 1
        ]

        # V7 fix (Q-2): impossible in a connected maze, but defensive.
        if not valid_moves:
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": "❌ Random Mouse: no valid moves (isolated cell).",
            }
            return

        r, c = random.choice(valid_moves)
        history.append((r, c))

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        yield {"type": "step", "r": r, "c": c, "steps": steps,
               "title": "Random Mouse (Chaos)", "restore": ".", "pq_info": "", "extra": {"algo": "random_mouse", "no_logic": True}}

    # unreachable
    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ Random Mouse: unexpected exit.",
    }