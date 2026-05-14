"""
algorithms/pathfinding/tremaux.py — Trémaux's Algorithm (1882).

The original "chalk mark" maze solving method. Marks passages on first
visit ('.') and double-marks them when backtracking ('x'). Guaranteed
to find a solution or prove none exists.

The key implementation detail: marks are on PASSAGES (edges), not cells.
A naive cell-visited approach breaks at 4-way junctions. Edge marks correctly
track which exits of a junction have been explored independently.
"""
from __future__ import annotations

import random
import time
from typing import Generator

from core.grid  import DIRECTIONS, terrain_cost
from core.graph import _deduplicate_path
from core.types import RunResult


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """Trémaux's Algorithm."""
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    # edge_marks[(min(a,b), max(a,b))] = traversal count (0, 1, or 2)
    edge_marks: dict[tuple, int] = {}

    def _ekey(a: tuple[int, int], b: tuple[int, int]) -> tuple:
        return (a, b) if a < b else (b, a)

    def _traverse(a: tuple[int, int], b: tuple[int, int]) -> None:
        k = _ekey(a, b)
        edge_marks[k] = edge_marks.get(k, 0) + 1

    def _marks(a: tuple[int, int], b: tuple[int, int]) -> int:
        return edge_marks.get(_ekey(a, b), 0)

    def _passable_neighbors(row: int, col: int) -> list[tuple[int, int]]:
        return [
            (row + dr, col + dc)
            for dr, dc in DIRECTIONS
            if 0 <= row + dr < rows and 0 <= col + dc < cols
            and maze[row + dr][col + dc] != 1
        ]

    r, c         = start
    prev: tuple[int, int] | None = None
    path_stack:  list[tuple[int, int]] = [(r, c)]
    steps        = 0
    compute_time = 0.0
    max_steps    = rows * cols * 4

    while True:
        t0 = time.perf_counter()

        if (r, c) == end:
            # Deduplicate path_stack before marking — on braided mazes a junction
            # can appear twice in the stack when re-entered via a different passage.
            # First-occurrence dedup causes teleportation gaps; loop-truncation fixes it.
            deduped = _deduplicate_path(path_stack)

            path_len  = 0
            path_cost = 0
            for pr, pc in deduped:
                if maze[pr][pc] not in {'S', 'E'}:
                    path_cost   += terrain_cost(maze[pr][pc])
                    maze[pr][pc] = 'P'
                    path_len    += 1
                    if fog is not None:
                        fog.add((pr, pc))
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(steps, compute_time, path_len, path_cost),
                "message": (
                    f"✅ SOLVED! | Steps: {steps} | "
                    f"Time: {compute_time * 1000:.2f} ms | "
                    f"Path: {path_len} | Cost: {path_cost}\n"
                    f"  📐 Steps = total moves incl. backtracking; "
                    f"Path = loop-free distance ({path_len} ≪ {steps} on deep mazes)"
                ),
            }
            return

        if steps >= max_steps:
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": "❌ Trémaux: step limit reached — no path found.",
            }
            return

        neighbors = _passable_neighbors(r, c)

        if not neighbors:
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": "❌ Trémaux: agent enclosed — no path found.",
            }
            return

        unvisited = [n for n in neighbors if _marks((r, c), n) == 0]

        restore: int | str

        if unvisited:
            # Rule 1: take any unvisited passage
            if maze[r][c] not in {'S', 'E', '~'}:
                maze[r][c] = '.'  # singly-mark current cell visually
            next_cell = random.choice(unvisited)
            _traverse((r, c), next_cell)
            prev = (r, c)
            r, c = next_cell
            path_stack.append((r, c))
            restore = '.'

        else:
            # Rule 2: no unvisited passages → backtrack via the entry passage
            if prev is None:
                compute_time += time.perf_counter() - t0
                yield {
                    "type":    "done",
                    "result":  RunResult(float('inf'), compute_time, 0, 0),
                    "message": "❌ Trémaux: no path found (all exits exhausted).",
                }
                return

            # Double-mark the dead end BEFORE leaving (the driver sets
            # maze[dest] = restore on the next yield, so we pre-stamp here)
            if maze[r][c] not in {'S', 'E', '~'}:
                maze[r][c] = 'x'

            next_cell = prev
            _traverse((r, c), next_cell)
            path_stack.pop()
            prev = path_stack[-2] if len(path_stack) >= 2 else None
            r, c = next_cell
            restore = maze[r][c] if maze[r][c] in {'.', 'x'} else '.'

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
            "title":   "Trémaux (Chalk marks)",
            "restore": restore,
            "pq_info": "",
        }

    yield {"type": "done", "result": RunResult(float('inf'), compute_time, 0, 0),
           "message": "❌ Trémaux: no path found."}
