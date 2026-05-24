"""
algorithms/pathfinding/bidirectional.py
-----------------------------------------
Bidirectional BFS — two simultaneous frontiers from S and E.

Generator contract: yields "step" dicts during dual-frontier expansion;
yields "done" when the frontiers collide or queues are exhausted.
"""

from __future__ import annotations

import time
from collections import deque
from typing      import Generator

from core.grid  import DIRECTIONS, PASSABLE, terrain_cost
from core.types import RunResult


def solve(
    maze:        list[list[int | str]],
    fog:         set[tuple[int, int]] | None = None,
    visit_count: dict[tuple[int, int], int]  | None = None,
) -> Generator[dict, None, None]:
    """
    Bidirectional BFS on *maze*.

    Two BFS waves expand from ``S`` (top-left) and ``E`` (bottom-right)
    simultaneously.  When the frontiers first meet, both parent chains
    are joined into a single solution path.

    Node-expansion saving
    ---------------------
    In the best case, Bidirectional BFS explores roughly O(b^(d/2))
    nodes per direction rather than O(b^d) for single-source BFS, where
    ``b`` is the branching factor and ``d`` is the solution depth.  On a
    uniform grid this can halve the number of cells examined.

    ⚠  Path-length caveat — READ BEFORE COMPARING WITH PLAIN BFS
    -------------------------------------------------------------
    Saving node expansions is NOT the same as guaranteeing a shorter
    path.  True hop-optimal Bidirectional BFS must finish expanding the
    ENTIRE current depth frontier on both sides before accepting a
    meeting node — a shorter path may exist through a different meeting
    cell at the same BFS depth.

    This implementation uses a best-total-tracking approach (``best_total``,
    ``candidates``) and prunes frontiers once their current depth alone
    reaches ``best_total``, which correctly finds the globally shortest
    meeting.  However, if you observe Bidirectional BFS returning a path
    longer than plain BFS, the cause is a subtle depth-level interaction —
    not a bug in BFS.  Diagnose by comparing ``result.path_len`` between
    the two algorithms in Race or Duel mode.

    Cost-blind: hop counts only.  Mud terrain is ignored.

    Yields:
        ``{"type": "step", ...}`` for every node expanded on either frontier.
        ``{"type": "done", ...}`` once solved or both queues are exhausted.
    """
    rows, cols = len(maze), len(maze[0])
    start, end = (0, 0), (rows - 1, cols - 1)

    queue_s:   deque[tuple[int, int]]                        = deque([start])
    queue_e:   deque[tuple[int, int]]                        = deque([end])
    visited_s: set[tuple[int, int]]                          = {start}
    visited_e: set[tuple[int, int]]                          = {end}
    parent_s:  dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    parent_e:  dict[tuple[int, int], tuple[int, int] | None] = {end:   None}

    # Hop-depth of each discovered node from its respective source.
    depth_s: dict[tuple[int, int], int] = {start: 0}
    depth_e: dict[tuple[int, int], int] = {end:   0}

    steps        = 0
    compute_time = 0.0

    # C-3 fix: track ALL meeting candidates and the minimum total path
    # length seen so far.  Do NOT break as soon as the first meeting node
    # is found — a shorter path may exist through a different node at the
    # same BFS depth.  Only prune a frontier once its current node depth
    # alone already equals or exceeds `best_total` (it cannot improve).
    best_total:   int | None            = None
    candidates:   list[tuple[int, int]] = []
    meeting:      tuple[int, int] | None = None

    # Edge-case guard: start == end (e.g. a 1×1 maze or identical corners).
    # Both visited sets already contain the node at initialisation, so it
    # will never be discovered as a *new* neighbour — candidates stays
    # empty forever and the algorithm falsely reports "no path found".
    # Detect and short-circuit before entering the BFS loop.
    if start == end:
        best_total = 0
        candidates = [start]
        queue_s.clear()
        queue_e.clear()

    while queue_s or queue_e:
        # ── Advance the forward (start) frontier ─────────────────────────
        if queue_s:
            t0     = time.perf_counter()
            curr_s = queue_s.popleft()
            rs, cs = curr_s
            d_s    = depth_s[curr_s]

            if best_total is not None and d_s >= best_total:
                # Any path through curr_s is ≥ best_total + 1 hops; skip.
                queue_s.clear()
            else:
                for dr, dc in DIRECTIONS:
                    nr, nc   = rs + dr, cs + dc
                    neighbor = (nr, nc)
                    if (
                        0 <= nr < rows and 0 <= nc < cols
                        and maze[nr][nc] in PASSABLE
                        and neighbor not in visited_s
                    ):
                        visited_s.add(neighbor)
                        parent_s[neighbor] = curr_s
                        depth_s[neighbor]  = d_s + 1
                        queue_s.append(neighbor)
                        if neighbor in visited_e:
                            total = depth_s[neighbor] + depth_e[neighbor]
                            if best_total is None or total < best_total:
                                best_total = total
                                candidates = [neighbor]
                            elif total == best_total:
                                candidates.append(neighbor)

            steps        += 1
            compute_time += time.perf_counter() - t0

            if fog is not None:
                fog.add((rs, cs))
            if visit_count is not None:
                visit_count[(rs, cs)] = visit_count.get((rs, cs), 0) + 1

            yield {"type": "step", "r": rs, "c": cs, "steps": steps, "extra": {"algo": "bidirectional", "frontier": "forward"},
                   "title": "Bidirectional BFS ← →", "restore": ".", "pq_info": ""}

        # ── Advance the backward (end) frontier ──────────────────────────
        if queue_e:
            t0     = time.perf_counter()
            curr_e = queue_e.popleft()
            re, ce = curr_e
            d_e    = depth_e[curr_e]

            if best_total is not None and d_e >= best_total:
                queue_e.clear()
            else:
                for dr, dc in DIRECTIONS:
                    nr, nc   = re + dr, ce + dc
                    neighbor = (nr, nc)
                    if (
                        0 <= nr < rows and 0 <= nc < cols
                        and maze[nr][nc] in PASSABLE
                        and neighbor not in visited_e
                    ):
                        visited_e.add(neighbor)
                        parent_e[neighbor] = curr_e
                        depth_e[neighbor]  = d_e + 1
                        queue_e.append(neighbor)
                        if neighbor in visited_s:
                            total = depth_s[neighbor] + depth_e[neighbor]
                            if best_total is None or total < best_total:
                                best_total = total
                                candidates = [neighbor]
                            elif total == best_total:
                                candidates.append(neighbor)

            steps        += 1
            compute_time += time.perf_counter() - t0

            if fog is not None:
                fog.add((re, ce))
            if visit_count is not None:
                visit_count[(re, ce)] = visit_count.get((re, ce), 0) + 1

            yield {"type": "step", "r": re, "c": ce, "steps": steps, "extra": {"algo": "bidirectional", "frontier": "backward"},
                   "title": "Bidirectional BFS ← →", "restore": ".", "pq_info": ""}

    meeting = candidates[0] if candidates else None

    if meeting is None:
        yield {
            "type":    "done",
            "result":  RunResult(float('inf'), compute_time, 0, 0),
            "message": "❌ Bidirectional BFS: no path found.",
        }
        return

    # ── Stitch the two parent chains into a single path ──────────────────
    t0 = time.perf_counter()

    path_s: list[tuple[int, int]] = []
    curr: tuple[int, int] | None  = meeting
    while curr is not None:
        path_s.append(curr)
        curr = parent_s.get(curr)
    path_s.reverse()

    path_e: list[tuple[int, int]] = []
    curr = parent_e.get(meeting)
    while curr is not None:
        path_e.append(curr)
        curr = parent_e.get(curr)

    path_len  = 0
    path_cost = 0
    for pr, pc in path_s + path_e:
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
        f"Path: {path_len} | Cost: {path_cost}"
    )
    yield {
        "type":    "done",
        "result":  RunResult(steps, compute_time, path_len, path_cost),
        "message": msg,
    }