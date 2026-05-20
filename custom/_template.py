"""
custom/_template.py — starting point for writing your own pathfinding algorithm.

Copy this file, rename it WITHOUT the underscore (e.g. my_algo.py), fill in the solve() function,
and the program will pick it up automatically on the next run.

The only hard requirement: a function named solve() that is a generator.
Everything else in this file is optional or just for reference.
"""

# ── What's in the maze ────────────────────────────────────────────────────────
#
# The maze is a list of lists: maze[row][col]
# Values you'll encounter:
#
#   1     — wall (impassable, do not enter)
#   0     — open passage (cost 1 to enter)
#   '~'   — mud (passable, cost 3)
#   'S'   — start cell — always at maze[0][0]
#   'E'   — exit cell  — always at maze[rows-1][cols-1]
#
# During animation the driver writes '@' onto the current cell temporarily,
# then restores it using the value you put in the "restore" key.
# The four cardinal directions as (row_delta, col_delta) offsets:
#
#   (-1, 0) = up    (1, 0) = down    (0, -1) = left    (0, 1) = right
#
# The imports below give you the shared constants so you don't have to
# redefine them yourself.

from __future__ import annotations

import time
from core.grid  import DIRECTIONS, PASSABLE, terrain_cost
from core.types import RunResult

# ── Optional metadata ─────────────────────────────────────────────────────────
#
# If PLUGIN_INFO is defined, the program uses it for the menu display.
# If it's missing, the filename is used instead (underscores → spaces, title-cased).
#
PLUGIN_INFO = {
    "name": "My Algorithm",          # shown in the menu
    "note": "brief description",     # shown next to the name
}


# ── solve() — the one required function ───────────────────────────────────────
#
# Called once per run. Must be a generator (uses yield, not return).
#
# Parameters:
#   maze         — the grid, list[list[int|str]]. You can read and write to it.
#   fog          — set of (row, col) that have been revealed. Add cells here
#                  as you visit them if Fog of War is enabled. Can be None.
#   visit_count  — dict mapping (row, col) → visit count, used for the heatmap.
#                  Increment it whenever you step on a cell. Can be None.
#
# IMPORTANT: keep all your state (visited set, queue, parent dict, etc.) as
# local variables INSIDE solve(). If you define them at module level, they'll
# persist between runs and cause wrong results on the second run.
#
# Returns (via the final yield): a RunResult with your stats.
#
def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
):
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    # ── your algorithm setup goes here ────────────────────────────────────────
    #
    # This example is a plain BFS so you can see the full structure.
    # Replace the queue/visited/parent logic with whatever you're implementing.

    from collections import deque
    queue   = deque([start])
    visited = {start}
    parent  = {start: None}
    steps   = 0
    compute_time = 0.0

    while queue:
        t0   = time.perf_counter()
        curr = queue.popleft()
        r, c = curr

        if curr == end:
            # ── mark the solution path ────────────────────────────────────────
            # Walk parent pointers back from end to start, stamp cells 'P'.
            # Skip S and E — they keep their own symbols.
            path_len = path_cost = 0
            node = end
            while node is not None:
                pr, pc = node
                if maze[pr][pc] not in {'S', 'E'}:
                    path_cost   += terrain_cost(maze[pr][pc])
                    maze[pr][pc] = 'P'
                    path_len    += 1
                    if fog is not None:
                        fog.add((pr, pc))
                node = parent[node]

            compute_time += time.perf_counter() - t0
            yield {
                "type":    "done",
                "result":  RunResult(steps, compute_time, path_len, path_cost),
                "message": (
                    f"✅ Done! | Steps: {steps} | "
                    f"Time: {compute_time * 1000:.2f} ms | "
                    f"Path: {path_len} | Cost: {path_cost}"
                ),
            }
            return

        for dr, dc in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < rows and 0 <= nc < cols
                and maze[nr][nc] in PASSABLE
                and (nr, nc) not in visited
            ):
                visited.add((nr, nc))
                parent[(nr, nc)] = curr
                queue.append((nr, nc))

        compute_time += time.perf_counter() - t0
        steps        += 1

        if fog is not None:
            fog.add((r, c))
        if visit_count is not None:
            visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

        # ── step yield ───────────────────────────────────────────────────────
        #
        # This tells the animation driver to draw '@' at (r, c), render the
        # frame, then restore the cell.
        #
        # "restore" should be the value maze[r][c] had BEFORE you visited it —
        # usually '.' after you first mark it, or '~' if it's mud.
        # If you don't mutate the maze during traversal, use ".".
        #
        # "pq_info" is the text shown in the Priority Queue Inspector panel.
        # Leave it "" unless your algorithm uses a heap and you want to show it.
        #
        yield {
            "type":    "step",
            "r":       r,
            "c":       c,
            "steps":   steps,
            "title":   "My Algorithm",   # appears in the Big-O HUD
            "restore": ".",
            "pq_info": "",
        }

    # Maze has no solution
    yield {
        "type":    "done",
        "result":  RunResult(float('inf'), compute_time, 0, 0),
        "message": "❌ My Algorithm: no path found.",
    }


# ── Quick reference ───────────────────────────────────────────────────────────
#
# PASSABLE cells (from core.grid):
#   frozenset({0, 'S', 'E', '~'})
#
# terrain_cost(cell) → int:
#   mud ('~') → 3, anything else → 1
#
# DIRECTIONS (from core.grid):
#   ((0,1), (1,0), (0,-1), (-1,0))   right / down / left / up
#
# RunResult fields:
#   steps        — nodes expanded (use float('inf') for failure)
#   compute_time — seconds (strip time.sleep() calls from this)
#   path_len     — interior cells in the solution path (not counting S/E)
#   path_cost    — weighted terrain cost of the solution path
#
# The program caps custom algorithms at 200,000 steps and shows a warning
# if that limit is hit, so you don't need to add your own infinite-loop guard.