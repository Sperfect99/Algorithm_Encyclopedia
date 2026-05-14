"""
treasure_gen.py — maze and treasure setup for the TSP/Treasure Hunt module.

Generates a maze, places N treasure points at well-spread locations,
and precomputes a full BFS distance matrix between all point pairs.
The path_matrix is what makes the TSP algorithms maze-aware — they
optimise over actual walkable paths, not straight-line distances.
"""

from __future__ import annotations

import random
import heapq


from maze_genV4 import generate_maze, add_terrain, MAZE_SIZES  # noqa: F401
# MAZE_SIZES is re-exported so treasure_solver.py needs no direct maze_genV4 import.

# ---------------------------------------------------------------------------
# Grid constants (used internally by BFS; not needed by the solver layer)
# ---------------------------------------------------------------------------

_DIRECTIONS: tuple[tuple[int, int], ...] = ((0, 1), (1, 0), (0, -1), (-1, 0))

# Maximum times generate_treasure_map will regenerate the maze before giving up.
MAX_GEN_RETRIES: int = 20


# ===========================================================================
# ── BFS PRIMITIVES ────────────────────────────────────────────────────────────
# ===========================================================================

def _bfs_from(
    maze:  list[list[int | str]],
    start: tuple[int, int],
) -> tuple[dict, dict]:
    """Dijkstra from start. Returns (dist, parent) dicts.

    Passable: 0, '~', 'S', 'E', 'T', 'c'. Walls (1) block movement.
    """
    rows, cols = len(maze), len(maze[0])
    dist:   dict[tuple[int, int], int]                    = {start: 0}
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    pq:     list[tuple[int, tuple[int, int]]]             = [(0, start)]

    while pq:
        d, (r, c) = heapq.heappop(pq)
        if d > dist.get((r, c), float('inf')):
            continue
        for dr, dc in _DIRECTIONS:
            nr, nc = r + dr, c + dc
            pos    = (nr, nc)
            if 0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] != 1:
                cost  = 3 if maze[nr][nc] == '~' else 1
                new_d = d + cost
                if pos not in dist or new_d < dist[pos]:
                    dist[pos]   = new_d
                    parent[pos] = (r, c)
                    heapq.heappush(pq, (new_d, pos))

    return dist, parent


def _reconstruct_bfs_path(
    parent: dict,
    end:    tuple[int, int],
) -> list[tuple[int, int]] | None:
    """Walk parent pointers from end back to root. Returns ordered path, or None if unreachable."""
    if end not in parent:
        return None
    path: list[tuple[int, int]] = []
    curr: tuple[int, int] | None = end
    while curr is not None:
        path.append(curr)
        curr = parent[curr]
    path.reverse()
    return path


# ===========================================================================
# ── TERRAIN COST ──────────────────────────────────────────────────────────────
# ===========================================================================

def terrain_cost(cell: int | str) -> int:
    """Cost to enter a cell. Mud costs 3, everything else 1."""
    return 3 if cell == '~' else 1


# ===========================================================================
# ── DISTANCE & PATH MATRIX ────────────────────────────────────────────────────
# ===========================================================================

def build_distance_matrix(
    maze:   list[list[int | str]],
    points: list[tuple[int, int]],
) -> tuple[list[list[float]], list[list[float]], list[list]]:
    """Build all-pairs cost and path matrices for the given key points.

    points[0] = S, points[1..N] = treasures.
    Returns (dist_matrix, cost_matrix, path_matrix) — all (N+1)×(N+1).
    Runs one Dijkstra per point: O(N·(V+E)logV) total.
    """
    N = len(points)
    dist_matrix: list[list[float]] = [[float('inf')] * N for _ in range(N)]
    cost_matrix: list[list[float]] = [[float('inf')] * N for _ in range(N)]
    path_matrix: list[list]        = [[None]         * N for _ in range(N)]

    # zero-cost self-loops on the diagonal
    for i in range(N):
        dist_matrix[i][i] = 0
        cost_matrix[i][i] = 0
        path_matrix[i][i] = [points[i]]

    for i, src in enumerate(points):
        dist, parent = _bfs_from(maze, src)
        for j, dst in enumerate(points):
            if i == j:
                continue
            if dst in dist:
                path = _reconstruct_bfs_path(parent, dst)
                dist_matrix[i][j] = dist[dst]
                path_matrix[i][j] = path
                # Weighted cost: sum terrain_cost for every cell *entered*.
                cost_matrix[i][j] = sum(
                    terrain_cost(maze[r][c]) for r, c in (path or [])[1:]
                )

    return dist_matrix, cost_matrix, path_matrix


# ===========================================================================
# ── TREASURE SCATTER ──────────────────────────────────────────────────────────
# ===========================================================================

def scatter_treasures(
    maze: list[list[int | str]],
    n:    int,
) -> list[tuple[int, int]]:
    """Scatter n treasures on reachable open cells of maze.

    Tries to space them out (min Manhattan gap) then falls back to
    random placement if the maze is too tight.
    Returns [S_pos, T1_pos, ..., Tn_pos].
    """
    rows, cols = len(maze), len(maze[0])
    start = (0, 0)
    e_pos = (rows - 1, cols - 1)

    dist, _ = _bfs_from(maze, start)
    candidates = [
        pos for pos in dist
        if maze[pos[0]][pos[1]] == 0   # road cells only — mud cells lose terrain
        and pos != start               # cost once overwritten by 'T' marker
        and pos != e_pos
    ]

    if len(candidates) < n:
        raise ValueError(
            f"Only {len(candidates)} reachable open cells; cannot place {n} treasures."
        )

    # Attempt spread-out placement with Manhattan spacing.
    min_spacing = max(3, (rows + cols) // max(3 * n, 1))
    random.shuffle(candidates)
    chosen: list[tuple[int, int]] = []

    for pos in candidates:
        if all(
            abs(pos[0] - p[0]) + abs(pos[1] - p[1]) >= min_spacing
            for p in chosen
        ):
            chosen.append(pos)
            if len(chosen) == n:
                break

    # Fill any remaining slots if spacing was too strict.
    if len(chosen) < n:
        extra = [p for p in candidates if p not in chosen]
        random.shuffle(extra)
        chosen.extend(extra[:n - len(chosen)])

    chosen = chosen[:n]
    for r, c in chosen:
        maze[r][c] = 'T'

    return [start] + chosen


# ===========================================================================
# ── PUBLIC ENTRY POINT ────────────────────────────────────────────────────────
# ===========================================================================

def generate_treasure_map(
    complexity:      int,
    num_treasures:   int,
    terrain_active:  bool,
    max_retries:     int = MAX_GEN_RETRIES,
) -> tuple[
    list[list[int | str]],   # maze  (with 'S' at (0,0), 'T' at treasure cells)
    list[tuple[int, int]],   # points  [S_pos, T1_pos, …, TN_pos]
    list[list[float]],       # dist_matrix
    list[list[float]],       # cost_matrix
    list[list],              # path_matrix
]:
    """
    Generate a complete, solver-ready treasure map.

    complexity     : int  — maze complexity level (0–10), forwarded to
                            'generate_maze()'.
    num_treasures  : int  — exact number of treasure cells to scatter.
    terrain_active : bool — whether to apply mud-terrain patches via
                            'add_terrain()'.
    max_retries    : int  — how many maze seeds to attempt before raising
                            (default: 'MAX_GEN_RETRIES = 20').

    Returns
    maze         : 2-D grid; cells modified in-place with ''T'' markers.
    points       : '[S_pos, T1_pos, …, TN_pos]'  (length = num_treasures + 1).
    dist_matrix  : Weighted terrain cost between all points.
    cost_matrix  : Weighted terrain cost between all points.
    path_matrix  : Actual cell-by-cell paths between all points.

    Raises:
    RuntimeError
        If a fully-connected map cannot be produced within *max_retries*
        attempts (extremely rare; typically maze is regenerated 0–2 times).

    Notes
    -----
    • This function is **pure generation** — no I/O, no animation.
    • The caller ('setup_treasure_maze' in 'treasure_solver.py') owns all
      user-facing prompts and progress messages.
    • Connectivity is guaranteed: every 'T' cell is reachable from 'S'.
      If any treasure is isolated, the maze is silently regenerated.
    """
    for attempt in range(max_retries):
        # ── 1. Generate base maze ─────────────────────────────────────────
        maze: list[list[int | str]] = generate_maze(complexity)
        if terrain_active:
            add_terrain(maze)

        # ── 2. Scatter treasures ──────────────────────────────────────────
        n_actual = num_treasures
        try:
            points = scatter_treasures(maze, n_actual)
        except ValueError:
            # Too few open cells for this seed — try a new maze.
            continue

        # ── 3. Build BFS matrices ─────────────────────────────────────────
        dist_matrix, cost_matrix, path_matrix = build_distance_matrix(maze, points)

        # ── 4. Connectivity check ─────────────────────────────────────────
        unreachable = [
            j for j in range(1, len(points))
            if dist_matrix[0][j] == float('inf')
        ]
        if unreachable:
            # Isolated treasure(s) — this maze seed is unusable; regenerate.
            continue

        # ── 5. All good — return solver-ready structures ──────────────────
        return maze, points, dist_matrix, cost_matrix, path_matrix

    # Exhausted all retries.
    raise RuntimeError(
        f"Could not generate a valid {complexity}-complexity treasure map with "
        f"{num_treasures} treasures after {max_retries} attempts. "
        "Try a larger maze or fewer treasures."
    )
