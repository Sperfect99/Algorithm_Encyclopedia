"""
algorithms/pathfinding/tremaux.py
-----------------------------------
Trémaux's Algorithm (1882 chalk-mark method).

Generator contract: yields "step" dicts with a ``restore`` value that
reflects the chalk-mark state ('.' or 'x'); yields "done" on completion.
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
    """
    Trémaux's Algorithm on *maze*.

    Marks passages with chalk (``'.'``) on first visit and double-marks
    (``'x'``) when backtracking from a dead end.  Guarantees a solution.
    The stack is used as the actual path — when the end is reached, its
    contents are the solution.

    Yields:
        ``{"type": "step", ..., "restore": "." | "x"}`` per step.
        ``{"type": "done", ...}`` once solved or stack exhausted.
    """
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    # ── M-9 fix: edge-based chalk marks ──────────────────────────────────
    #
    # Original implementation used a `visited` SET of cells, which cannot
    # distinguish "I entered junction J from the west and haven't tried
    # east" from "I have fully explored all exits of J."  At a 4-way
    # junction this collapses the two-mark rule into unreliable DFS.
    #
    # Correct Trémaux invariant: mark PASSAGES (undirected edges), not
    # cells.  An edge traversed once is "singly marked" (chalk dot); an
    # edge traversed twice is "doubly marked" (dead-end confirmed).  The
    # passage to a neighbor is "unvisited" iff its mark count is 0.
    #
    # Rule at each junction (current cell, entered from `prev`):
    #   1. Unvisited passages exist → choose any at random, mark it once.
    #   2. No unvisited passages → backtrack via `prev`, marking that edge
    #      a second time (doubly-marking the dead-end passage).
    #
    # This correctly handles multiply-connected junctions: a cell can be
    # visited many times via different passages; the marks on those
    # passages independently track which exits have been explored.
    #
    # `path_stack` tracks the current path from start to the agent so the
    # solution can be reconstructed directly when the exit is reached.

    # edge_marks[(min(a,b), max(a,b))] = traversal count (0, 1, or 2)
    edge_marks: dict[tuple, int] = {}

    def _ekey(
        a: tuple[int, int], b: tuple[int, int]
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Canonical undirected edge key — always (smaller, larger)."""
        return (a, b) if a < b else (b, a)

    def _traverse(a: tuple[int, int], b: tuple[int, int]) -> None:
        """Increment the mark count on passage a↔b."""
        k = _ekey(a, b)
        edge_marks[k] = edge_marks.get(k, 0) + 1

    def _marks(a: tuple[int, int], b: tuple[int, int]) -> int:
        """Return the current mark count on passage a↔b."""
        return edge_marks.get(_ekey(a, b), 0)

    def _passable_neighbors(
        row: int, col: int
    ) -> list[tuple[int, int]]:
        return [
            (row + dr, col + dc)
            for dr, dc in DIRECTIONS
            if (
                0 <= row + dr < rows and 0 <= col + dc < cols
                and maze[row + dr][col + dc] != 1
            )
        ]

    r, c         = start
    prev: tuple[int, int] | None = None   # cell we entered current cell from
    path_stack:  list[tuple[int, int]]   = [(r, c)]
    steps        = 0
    compute_time = 0.0
    max_steps    = rows * cols * 4        # generous but finite safety cap

    while True:
        t0 = time.perf_counter()

        # ── Goal check ────────────────────────────────────────────────────
        if (r, c) == end:
            # Deduplicate path_stack before measuring cost and length.
            #
            # Trémaux's invariant keeps path_stack as the agent's live route
            # from start to the current cell, popping dead-ends on backtrack.
            # On a braided maze a junction cell can be appended a second time
            # when the agent re-enters it via a NEW (unvisited) passage before
            # any backtrack pops it.  First-occurrence-wins dedup on
            # [S,A,B,C,A,D,E] yields [S,A,B,C,D,E] where C→D is not adjacent
            # (teleportation gap).  Loop-truncation correctly produces [S,A,D,E].
            deduped_stack: list[tuple[int, int]] = _deduplicate_path(path_stack)

            path_len  = 0
            path_cost = 0
            for pr, pc in deduped_stack:
                if maze[pr][pc] not in {'S', 'E'}:
                    path_cost   += terrain_cost(maze[pr][pc])
                    maze[pr][pc] = 'P'
                    path_len    += 1
                    if fog is not None:
                        fog.add((pr, pc))
            compute_time += time.perf_counter() - t0
            msg = (
                f"✅ SOLVED! | Steps: {steps} | "
                f"Time: {compute_time * 1000:.2f} ms | "
                f"Path: {path_len} | Cost: {path_cost}\n"
                f"  📐 Steps = total moves incl. backtracking; "
                f"Path = loop-free distance ({path_len} ≪ {steps} on deep mazes)"
            )
            yield {
                "type":    "done",
                "result":  RunResult(steps, compute_time, path_len, path_cost),
                "message": msg,
            }
            return

        # ── Step-limit guard ──────────────────────────────────────────────
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
            # Completely enclosed cell — algorithm cannot proceed.
            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(float('inf'), compute_time, 0, 0),
                "message": "❌ Trémaux: agent enclosed — no path found.",
            }
            return

        # Passages with zero marks from here → unvisited by Trémaux rules.
        unvisited = [n for n in neighbors if _marks((r, c), n) == 0]

        restore: int | str

        if unvisited:
            # ── Rule 1: forward step on any unvisited passage ─────────────
            if maze[r][c] not in {'S', 'E', '~'}:
                maze[r][c] = '.'          # singly-mark current cell visually
            next_cell = random.choice(unvisited)
            _traverse((r, c), next_cell)  # passage now singly-marked
            prev = (r, c)
            r, c = next_cell
            path_stack.append((r, c))
            restore = '.'

        else:
            # ── Rule 2: no unvisited passages → backtrack via entry edge ──
            # Double-marking the entry passage confirms the current cell is
            # a dead end (or a junction fully explored from this direction).
            if prev is None:
                # At start with no unvisited exits — maze has no solution.
                compute_time += time.perf_counter() - t0
                yield {
                    "type":    "done",
                    "result":  RunResult(float('inf'), compute_time, 0, 0),
                    "message": "❌ Trémaux: no path found (all exits exhausted).",
                }
                return

            # Mark dead-end visually BEFORE leaving (the animation driver
            # sets maze[destination] = restore on the NEXT yield, so we must
            # pre-stamp the cell we are departing from here).
            if maze[r][c] not in {'S', 'E', '~'}:
                maze[r][c] = 'x'          # doubly-mark dead-end cell visually
                
            next_cell = prev
            _traverse((r, c), next_cell)  # entry passage now doubly-marked
            path_stack.pop()              # remove dead-end from solution path

            # Update prev to the cell before the new current position.
            prev = path_stack[-2] if len(path_stack) >= 2 else None
            r, c = next_cell
            # Preserve the visual state of the cell we are returning to.
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
            "extra": {"algo": "tremaux", "marks_here": sum(_marks(curr, (r+dr, c+dc)) for dr,dc in ((-1,0),(0,1),(1,0),(0,-1)))},
        }

    # Unreachable — satisfies type checkers.
    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ Trémaux: no path found.",
    }