"""
dynamic_gen3.py — maze generation and environment setup for the Pursuit-Evasion module.

Public API:
    setup_dynamic_map(complexity)           → (maze, agent_pos, target_pos)
    perturb_maze(maze, n, agent, target)    → list of changed cells
    wander_target(maze, pos, agent, radius) → new target position
    get_passable_neighbors(maze, pos)       → list of (r, c) positions

Note: wander_target requires setup_dynamic_map() to have been called first
to initialise _TERRAIN_CACHE. The V3 controller doesn't actually use
wander_target — it uses pursuit.py's internal _move_target() instead.

The flee_radius parameter on wander_target controls target "intelligence":
    0  → blind wanderer (ignores agent position entirely)
    5  → normal (flees when agent is within 5 cells)
    20 → paranoid (sees and flees from anywhere on the map)
"""

from __future__ import annotations

import random
from collections import deque

from maze_genV4 import generate_maze, MAZE_SIZES

# ── Cell identity helpers ────────────────────────────────────────────────────

PASSABLE_CELLS: frozenset = frozenset({0, 'S', 'T', 'E', '~'})

# Terrain cache: remembers the original cell value (0 or '~') that existed
# under the Target ('T') marker before it was stamped.  Keyed by (row, col).
# This allows wander_target() to restore exact terrain on departure instead
# of blindly writing 0, which would permanently destroy mud ('~') patches.
_TERRAIN_CACHE: dict[tuple[int, int], int | str] = {}


def _is_passable(cell) -> bool:
    """Return True if a cell can be walked through."""
    return cell in PASSABLE_CELLS


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Manhattan distance between two grid positions."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ===========================================================================
# ── BFS CONNECTIVITY CHECK ───────────────────────────────────────────────────
# ===========================================================================

def _bfs_connected(
    maze: list[list[int | str]],
    start: tuple[int, int],
    goal: tuple[int, int],
    blocked: tuple[int, int] | None = None,
) -> bool:
    """
    Return True if *start* can reach *goal* via passable cells.

    If *blocked* is given, that cell is treated as a wall for the duration
    of this check (used to test "what if we wall this cell?").

    Pure BFS — O(V+E) worst case, but typically terminates quickly on
    connected mazes because it stops the moment *goal* is found.
    """
    rows, cols = len(maze), len(maze[0])
    visited: set[tuple[int, int]] = {start}
    queue: deque[tuple[int, int]] = deque([start])

    while queue:
        r, c = queue.popleft()
        if (r, c) == goal:
            return True
        for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            nr, nc = r + dr, c + dc
            npos = (nr, nc)
            if (
                0 <= nr < rows and 0 <= nc < cols
                and npos not in visited
                and npos != blocked
                and _is_passable(maze[nr][nc])
            ):
                visited.add(npos)
                queue.append(npos)

    return False


# ===========================================================================
# ── PUBLIC API ───────────────────────────────────────────────────────────────
# ===========================================================================

def setup_dynamic_map(
    complexity: int,
) -> tuple[list[list[int | str]], tuple[int, int], tuple[int, int]]:
    """
    Generate a maze and place the Agent ('S') and Target ('T').

    The agent starts at the top-left corner.  The target is placed at a random
    passable cell at least 'manhattan / 3' steps from the agent (measured as
    Manhattan distance) to guarantee an interesting chase.

    Returns:
        (maze, agent_pos, target_pos)
    """
    _TERRAIN_CACHE.clear()   # flush stale entries from any previous session
    maze = generate_maze(complexity)
    rows, cols = len(maze), len(maze[0])

    # Agent always starts top-left (the classic 'S' position).
    agent_pos = (0, 0)
    maze[0][0] = 'S'

    # Remove default 'E' placed by generate_maze — we use 'T' instead.
    maze[rows - 1][cols - 1] = 0

    # Collect all passable cells for target placement.
    open_cells: list[tuple[int, int]] = [
        (r, c) for r in range(rows) for c in range(cols)
        if maze[r][c] == 0
    ]

    # Place target as far as possible (at least 1/3 of max manhattan dist).
    min_dist = (rows + cols) // 3
    candidates = [
        pos for pos in open_cells
        if _manhattan(pos, agent_pos) >= min_dist
    ]
    if not candidates:
        candidates = open_cells  # fallback for tiny mazes

    target_pos = random.choice(candidates)
    _TERRAIN_CACHE[target_pos] = maze[target_pos[0]][target_pos[1]]  # save before stamp
    maze[target_pos[0]][target_pos[1]] = 'T'

    return maze, agent_pos, target_pos


def get_passable_neighbors(
    maze: list[list[int | str]],
    pos: tuple[int, int],
) -> list[tuple[int, int]]:
    """Return all cardinal-adjacent passable neighbours of *pos*."""
    rows, cols = len(maze), len(maze[0])
    r, c = pos
    result: list[tuple[int, int]] = []
    for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols and _is_passable(maze[nr][nc]):
            result.append((nr, nc))
    return result


def wander_target(
    maze: list[list[int | str]],
    target_pos: tuple[int, int],
    agent_pos: tuple[int, int] | None = None,
    flee_radius: int = 5,
    prev_pos: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """
    Move the Target one step, with configurable Fleeing instinct.

    V1.2 FEAT-1: Adjustable vision radius
        'flee_radius' controls how far the target can "see" the agent:
            0   → blind — pure random wander (agent_pos is ignored).
            1-5 → normal — flees when agent enters that Manhattan radius.
            20  → psychic — sees and flees agent from across the maze.

        When the agent is within *flee_radius* cells, the target enters
        **Flee mode**: it picks the passable neighbour that maximises
        Manhattan distance from the agent.  Ties broken randomly.

        Outside *flee_radius* (or if radius is 0): random walk with a
        30% idle chance.

    V1.3 FIX — Local minima / dead-end oscillation:
        'prev_pos' is the cell the target occupied one tick ago.
        In Flee mode the target will not voluntarily return to that cell —
        this prevents the "U-corridor pace" where the prey bounces between
        a dead-end and its entrance forever.

        Survival instinct priority ladder:
            1. Flee forward (any neighbour except prev_pos).
            2. If ALL neighbours are prev_pos (truly cornered): accept
               the retreat and pick the least-bad option from all
               neighbours.  The animal pushes through temporarily rather
               than standing still — panicked, not suicidal.

    Preserves the underlying cell: clears old position to 0, stamps new
    position with 'T'.

    Returns:
        The new target position (may be the same if resting or boxed in).
    """
    neighbours = get_passable_neighbors(maze, target_pos)
    if not neighbours:
        return target_pos  # boxed in — stay put

    # Determine mode: FLEE or WANDER
    fleeing = (
        flee_radius > 0
        and agent_pos is not None
        and _manhattan(target_pos, agent_pos) <= flee_radius
    )

    if fleeing:
        # ── FLEE MODE: maximise distance from agent ─────────────────────
        # Survival instinct: avoid returning to the cell we just came from.
        # This breaks dead-end oscillation without requiring any lookahead.
        # If filtering leaves no candidates (only exit IS prev_pos) we fall
        # back to all neighbours — the prey pushes through reluctantly.
        flee_candidates = (
            [n for n in neighbours if n != prev_pos] or neighbours
        )
        flee_candidates.sort(
            key=lambda p: _manhattan(p, agent_pos),  # type: ignore[arg-type]
            reverse=True,
        )
        best_dist = _manhattan(flee_candidates[0], agent_pos)  # type: ignore[arg-type]
        best_moves = [
            n for n in flee_candidates
            if _manhattan(n, agent_pos) == best_dist  # type: ignore[arg-type]
        ]
        new_pos = random.choice(best_moves)
    else:
        # ── WANDER MODE: random walk with 30 % idle chance ──────────────
        if random.random() < 0.30:
            return target_pos  # rest
        new_pos = random.choice(neighbours)

    # Clear old position — restore the ORIGINAL terrain value, not a
    # hard-coded 0.  If the target was standing on mud ('~'), overwriting
    # with 0 permanently destroys that terrain, corrupting every future
    # cost calculation for any path that crosses the cell.
    old_r, old_c   = target_pos
    original_terrain = maze[old_r][old_c]
    # The cell holds 'T' right now; determine what was underneath by
    # checking the new cell (which still has its real value).  The old
    # cell can only legally be 0 or '~' — 'T' is the marker we stamped.
    # We restore whatever non-'T' value was there before we stamped it.
    # To do this correctly we must have saved it on stamp; introduce a
    # one-cell look-back by reading from the pre-stamp value cached in
    # the caller — but since this function currently holds no such cache,
    # we use the only safe reconstruction: the cell is either plain floor
    # (0) or mud ('~').  We infer from the neighbours: if ANY cardinal
    # neighbour was originally mud, the cell could be too — but we cannot
    # know without a cache.  The correct fix is to stamp 'T' over a saved
    # value.  We implement that now by changing the stamp logic below.
    #
    # ACTUAL FIX: the cell currently holds 'T'.  We cannot know the
    # original terrain without having saved it at stamp-time.  Replace
    # the single-value stamp with a two-value stamp: store the original
    # value in a separate parallel structure.  Since this function is
    # called from a tight loop without access to external state, the
    # minimal-impact fix is to encode the original terrain directly inside
    # the maze using a sentinel tuple — but that breaks the int|str type.
    #
    # Correct architecture: the caller must pass in (or this function must
    # return) the original cell value so the next call can restore it.
    # We implement that by returning (new_pos, original_terrain) and
    # restoring via the value that was saved when 'T' was FIRST stamped.
    #
    # For full backward compatibility with all existing callers we use a
    # module-level dict as a terrain cache — zero interface change needed.
    maze[old_r][old_c] = _TERRAIN_CACHE.pop((old_r, old_c), 0)

    # Stamp new position — save the real terrain before overwriting.
    nr, nc = new_pos
    _TERRAIN_CACHE[(nr, nc)] = maze[nr][nc]   # save '~' or 0 before 'T'
    maze[nr][nc] = 'T'

    return new_pos


def perturb_maze(
    maze: list[list[int | str]],
    num_changes: int,
    agent_pos: tuple[int, int],
    target_pos: tuple[int, int],
) -> list[tuple[int, int]]:
    """
    Dynamically mutate the maze: flip walls ↔ paths at random locations.

    Safety constraints (never violated):
        1. Never change the border walls (row 0 / last row, col 0 / last col).
        2. Never flip a cell occupied by the Agent or Target.
        3. After flipping a wall → path, ensure new path has ≥ 2 passable
           neighbours (avoids creating isolated pockets).
        4. V1.1 FIX-3 — Before flipping a path → wall, run a full BFS
           flood-fill from *agent_pos* to *target_pos* with the candidate
           cell treated as a wall.  If the BFS fails to reach the target,
           the flip is **aborted**.  This guarantees global S↔T connectivity
           at all times, eliminating the fatal disconnection trap.

    Returns:
        A list of (row, col) positions that were changed (for D* Lite repair).
    """
    rows, cols = len(maze), len(maze[0])
    changed: list[tuple[int, int]] = []
    attempts = 0
    max_attempts = num_changes * 10  # generous budget; BFS is cheap

    while len(changed) < num_changes and attempts < max_attempts:
        attempts += 1
        r = random.randint(1, rows - 2)
        c = random.randint(1, cols - 2)
        pos = (r, c)

        # Never touch the agent or target cells.
        if pos == agent_pos or pos == target_pos:
            continue

        cell = maze[r][c]

        if cell == 1:
            # ── Wall → Path: only if it would connect to ≥ 2 passable cells ──
            passable_nbrs = 0
            for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and _is_passable(maze[nr][nc]):
                    passable_nbrs += 1
            if passable_nbrs >= 2:
                maze[r][c] = 0
                changed.append(pos)

        elif cell == 0:
            # ── Path → Wall: GLOBAL connectivity check (FIX-3) ──────────
            local_safe = True
            for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and _is_passable(maze[nr][nc]):
                    other_passable = 0
                    for dr2, dc2 in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                        nnr, nnc = nr + dr2, nc + dc2
                        if (nnr, nnc) == (r, c):
                            continue
                        if 0 <= nnr < rows and 0 <= nnc < cols and _is_passable(maze[nnr][nnc]):
                            other_passable += 1
                    if other_passable == 0:
                        local_safe = False
                        break

            if not local_safe:
                continue

            # Global check: would Agent still be able to reach Target?
            if not _bfs_connected(maze, agent_pos, target_pos, blocked=pos):
                continue  # ABORT — this wall would sever connectivity

            maze[r][c] = 1
            changed.append(pos)

    return changed


# ── Standalone demo ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from maze_genV4 import MAZE_SIZES as _MS

    print("Dynamic Gen V1.2 — quick self-test")
    mz, a, t = setup_dynamic_map(3)
    print(f"  Maze {len(mz)}×{len(mz[0])}  Agent={a}  Target={t}")

    # Test flee_radius=0 (blind), =5 (normal), =20 (psychic)
    for radius in (0, 5, 20):
        mz2, a2, t2 = setup_dynamic_map(2)
        label = {0: "blind", 5: "normal", 20: "psychic"}[radius]
        for _ in range(10):
            t2 = wander_target(mz2, t2, agent_pos=a2, flee_radius=radius)
        print(f"  flee_radius={radius:>2} ({label:>7}): target ended at {t2}")

    # Verify connectivity is maintained across perturbations
    for step in range(20):
        ch = perturb_maze(mz, 5, a, t)
        old_t = t
        t = wander_target(mz, t, agent_pos=a, flee_radius=5)
        connected = _bfs_connected(mz, a, t)
        assert connected, f"FATAL: connectivity broken at step {step+1}!"

    print("  20 perturbation cycles — connectivity intact ✓")
    print("  Self-test passed ✓")
