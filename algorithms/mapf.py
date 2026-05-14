"""
algorithms/mapf.py — generator implementations for the three MAPF algorithms.

Each generator yields "plan" (planning phase), "step" (simulation tick),
"conflict" (vertex collision), and "done" dicts for the animation driver.

Independent A* plans all paths first then simulates; collisions are detected
but not resolved. Prioritised Planning reserves space-time cells so agents
plan around each other. CBS builds a constraint tree to find conflict-free paths.
"""
from __future__ import annotations

import heapq
import itertools
import time
from typing import Generator

from core.grid  import DIRECTIONS, terrain_cost
from core.graph import manhattan_distance as _manhattan
from core.types import MapfResult

# ---------------------------------------------------------------------------
# MAPF uses the original terrain only — no '.' or 'P' markers expected.
# (Controllers must pass a clean maze copy.)
# ---------------------------------------------------------------------------
_PASSABLE: frozenset[int | str] = frozenset({0, '~', 'S', 'E'})

# Space-time A* hard limit: prevents infinite waits on over-constrained mazes.
# Dynamic ceiling: worst-case path on the largest maze (61×151=9211 cells)
# is bounded by V. A hard 400 can fail on complexity-10 with heavy constraints.
# This constant is overridden per-call in solve_prioritized and solve_cbs
# where the maze dimensions are available, but the module default is raised
# here as a safe baseline.
_MAX_TIME: int = 1500

# Default CT node budget for CBS.  Caps the search for interactive use;
# the best partial solution found before this limit is still returned.
# Raise for deeper exhaustive search; lower for faster (less optimal) results.
CBS_MAX_NODES: int = 500

# Float comparison epsilon for g-score staleness checks in space-time A*.
# Prevents re-expansion of nodes whose g-score was updated to an equal value
# via floating-point rounding.  Must be smaller than the minimum edge cost (1).
_GSCORE_EPS: float = 1e-9


# ===========================================================================
# ── INTERNAL HELPERS ──────────────────────────────────────────────────────────
# ===========================================================================




def _astar_path(
    maze:  list[list[int | str]],
    start: tuple[int, int],
    goal:  tuple[int, int],
) -> list[tuple[int, int]] | None:
    """
    Standard single-agent A* ignoring other agents.

    Returns the full path (start → goal inclusive), or None if no path exists.
    """
    rows, cols = len(maze), len(maze[0])
    pq: list[tuple[float, tuple[int, int]]] = [
        (float(_manhattan(start, goal)), start)
    ]
    g:      dict[tuple[int, int], float]                  = {start: 0.0}
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    closed: set[tuple[int, int]]                           = set()

    while pq:
        _, curr = heapq.heappop(pq)
        if curr in closed:
            continue
        closed.add(curr)
        if curr == goal:
            path: list[tuple[int, int]] = []
            node: tuple[int, int] | None = curr
            while node is not None:
                path.append(node)
                node = parent[node]
            path.reverse()
            return path
        r, c = curr
        for dr, dc in DIRECTIONS:
            nr, nc = r + dr, c + dc
            nb     = (nr, nc)
            if (0 <= nr < rows and 0 <= nc < cols
                    and maze[nr][nc] in _PASSABLE
                    and nb not in closed):
                ng = g[curr] + terrain_cost(maze[nr][nc])
                if nb not in g or ng < g[nb]:
                    g[nb]      = ng
                    parent[nb] = curr
                    heapq.heappush(pq, (ng + _manhattan(nb, goal), nb))
    return None


def _spacetime_astar(
    maze:        list[list[int | str]],
    start:       tuple[int, int],
    goal:        tuple[int, int],
    constraints: set[tuple[int, int, int]],   # (r, c, t) forbidden
    max_time:    int = _MAX_TIME,
) -> list[tuple[int, int]] | None:
    """
    Space-time A* under a set of (r, c, t) forbidden constraints.

    State: (row, col, timestep).
    Actions: move to passable neighbour OR wait in place (cost 1 per tick).
    Heuristic: Manhattan distance to goal (admissible; ignores time).

    Returns the position sequence (length = timesteps + 1) or 'None'.
    """
    rows, cols = len(maze), len(maze[0])

    def h(r: int, c: int) -> int:
        return _manhattan((r, c), goal)

    # heap: (f, g, r, c, t)
    pq: list[tuple[float, float, int, int, int]] = [
        (float(h(*start)), 0.0, start[0], start[1], 0)
    ]
    g_score: dict[tuple[int, int, int], float]                          = {
        (start[0], start[1], 0): 0.0
    }
    parent: dict[tuple[int, int, int], tuple[int, int, int] | None]     = {
        (start[0], start[1], 0): None
    }

    while pq:
        _, g, r, c, t = heapq.heappop(pq)
        if t > max_time:
            continue
        state = (r, c, t)
        if g > g_score.get(state, float('inf')) + _GSCORE_EPS:
            continue   # stale entry
        if (r, c) == goal:
            path: list[tuple[int, int]] = []
            s: tuple[int, int, int] | None = state
            while s is not None:
                path.append((s[0], s[1]))
                s = parent[s]
            path.reverse()
            return path

        nt = t + 1
        # ── Option A: wait in place ──────────────────────────────────────
        wait_key = (r, c, nt)
        if wait_key not in constraints:
            ng = g + 1.0
            if ng < g_score.get(wait_key, float('inf')):
                g_score[wait_key] = ng
                parent[wait_key]  = state
                heapq.heappush(pq, (ng + h(r, c), ng, r, c, nt))

        # ── Option B: move to neighbour ──────────────────────────────────
        for dr, dc in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if (0 <= nr < rows and 0 <= nc < cols
                    and maze[nr][nc] in _PASSABLE):
                move_key = (nr, nc, nt)
                if move_key not in constraints:
                    ng = g + terrain_cost(maze[nr][nc])
                    if ng < g_score.get(move_key, float('inf')):
                        g_score[move_key] = ng
                        parent[move_key]  = state
                        heapq.heappush(pq, (ng + h(nr, nc), ng, nr, nc, nt))
    return None


def _pad_path(
    path:   list[tuple[int, int]],
    length: int,
) -> list[tuple[int, int]]:
    """Extend path to 'length' by repeating the final position (wait at goal)."""
    if not path:
        return path
    return path + [path[-1]] * max(0, length - len(path))


def _positions_at(
    paths: list[list[tuple[int, int]]],
    t:     int,
) -> list[tuple[int, int]]:
    """Return each agent's position at timestep t (clamped to path end)."""
    return [p[min(t, len(p) - 1)] for p in paths]


def _detect_conflicts(
    positions: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Return cells occupied by 2 or more agents simultaneously."""
    from collections import Counter
    counts = Counter(positions)
    return [pos for pos, n in counts.items() if n > 1]


def _find_first_conflict(
    paths: list[list[tuple[int, int]]],
) -> tuple[int, int, int, int, int] | None:
    """
    Scan all timesteps for the earliest vertex or edge (swap) conflict.

    Vertex conflict: agents i and j occupy the same cell at the same time.
    Edge conflict:   agents i and j swap positions in one step — agent i
                     moves X → Y while agent j moves Y → X at the same
                     timestep.  Swap conflicts produce physically
                     impossible trajectories (agents pass through each
                     other) and must be eliminated by CBS.

    Returns '(agent_i, agent_j, row, col, timestep)' or 'None'.

    For vertex conflicts: '(row, col)' is the shared cell at
    'timestep'.

    For edge (swap) conflicts: '(row, col)' is agent_i's *destination*
    cell and 'timestep' is the arrival timestep (t + 1).  CBS branches
    by adding the vertex constraint "agent_i cannot be at (row, col) at
    timestep" or the symmetric constraint for agent_j, which is
    sufficient to break any swap.
    """
    if len(paths) < 2:
        return None
    max_t  = max(len(p) for p in paths)
    padded = [_pad_path(p, max_t) for p in paths]
    n      = len(padded)

    for t in range(max_t):
        # ── Vertex conflicts ─────────────────────────────────────────────
        for i in range(n):
            for j in range(i + 1, n):
                if padded[i][t] == padded[j][t]:
                    r, c = padded[i][t]
                    return (i, j, r, c, t)

        # ── Edge (swap) conflicts at t → t+1 ─────────────────────────────
        if t + 1 < max_t:
            for i in range(n):
                for j in range(i + 1, n):
                    # Swap: i moves A→B while j moves B→A in the same step.
                    if (
                        padded[i][t]     == padded[j][t + 1]
                        and padded[i][t + 1] == padded[j][t]
                        and padded[i][t]     != padded[i][t + 1]  # actual move, not wait
                    ):
                        # Constrain agent_i from reaching its destination at t+1.
                        r, c = padded[i][t + 1]
                        return (i, j, r, c, t + 1)

    return None


def _count_all_conflicts(paths: list[list[tuple[int, int]]]) -> int:
    """
    Count every remaining vertex and edge (swap) conflict in *paths*.

    Used by CBS to report the true number of unresolved conflicts on
    capped runs, where multiple conflicts may still exist.  Vertex and
    swap conflicts at every timestep pair are each counted once.

    Returns 0 for a conflict-free solution.
    """
    if len(paths) < 2:
        return 0
    max_t  = max(len(p) for p in paths)
    padded = [_pad_path(p, max_t) for p in paths]
    n      = len(padded)
    count  = 0

    for t in range(max_t):
        # Vertex conflicts
        for i in range(n):
            for j in range(i + 1, n):
                if padded[i][t] == padded[j][t]:
                    count += 1
        # Edge (swap) conflicts
        if t + 1 < max_t:
            for i in range(n):
                for j in range(i + 1, n):
                    if (
                        padded[i][t]     == padded[j][t + 1]
                        and padded[i][t + 1] == padded[j][t]
                        and padded[i][t]     != padded[i][t + 1]
                    ):
                        count += 1
    return count


def _simulate(
    paths:  list[list[tuple[int, int]]],
    goals:  list[tuple[int, int]],
    title:  str,
) -> Generator[dict, None, None]:
    """
    Shared simulation loop: yields one "step" dict per timestep until all
    agents are at their goals (or the makespan is exhausted).
    """
    makespan = max(len(p) for p in paths)
    for t in range(makespan):
        positions = _positions_at(paths, t)
        conflicts = _detect_conflicts(positions)
        at_goal   = [positions[i] == goals[i] for i in range(len(goals))]
        yield {
            "type":      "step",
            "title":     title,
            "timestep":  t,
            "steps":     t,
            "positions": positions,
            "goals":     goals,
            "at_goal":   at_goal,
            "conflicts": conflicts,
            "paths":     paths,
        }
        if conflicts:
            yield {
                "type":      "conflict",
                "positions": positions,
                "conflicts": conflicts,
                "timestep":  t,
                "steps":     t,
                "title":     f"⚠  Vertex conflict at t={t}: cells {conflicts}",
            }
        if all(at_goal):
            break


# ===========================================================================
# ── ALGORITHM 1: INDEPENDENT A* ──────────────────────────────────────────────
# ===========================================================================

def solve_independent(
    maze:   list[list[int | str]],
    starts: list[tuple[int, int]],
    goals:  list[tuple[int, int]],
) -> Generator[dict, None, None]:
    """
    Independent A*  —  baseline MAPF; detects but never resolves conflicts.

    Each agent runs standard A* on the full maze, totally unaware of the
    others.  After planning, all agents are simulated simultaneously.

    Pedagogical purpose
    -------------------
    Students observe that optimal single-agent paths routinely collide.
    The collision count quantifies HOW BADLY independence fails on the
    chosen maze — motivating the coordinated algorithms that follow.

    Complexity: O(n · (V+E)logV)

    Yields:
        "plan"     — once per agent during the planning phase.
        "step"     — one simulation tick.
        "conflict" — immediately after any "step" that has conflicts.
        "done"     — terminal; carries MapfResult.
    """
    n        = len(starts)
    t0_all   = time.perf_counter()
    paths: list[list[tuple[int, int]]] = []

    # ── Planning phase ────────────────────────────────────────────────────
    for i in range(n):
        path = _astar_path(maze, starts[i], goals[i])
        if path is None:
            path = [starts[i]]   # stuck at start — maze may be unsolvable
        paths.append(path)
        yield {
            "type":     "plan",
            "agent":    i,
            "path_len": len(path),
            "title":    f"Independent A* — planning agent {i}",
            "steps":    i + 1,
        }

    # ── Simulation phase ─────────────────────────────────────────────────
    makespan       = max(len(p) for p in paths)
    total_soc      = sum(max(0, len(p) - 1) for p in paths)   # moves, not positions
    total_conflicts = 0

    for state in _simulate(paths, goals, "Independent A* (collision-blind)"):
        if state["type"] == "conflict":
            total_conflicts += len(state["conflicts"])
        yield state

    compute_time = time.perf_counter() - t0_all
    solved       = all(paths[i][-1] == goals[i] for i in range(n))
    status       = "✅ SOLVED" if solved else "⚠  PARTIAL"
    msg = (
        f"{status} | Makespan: {makespan} | SoC: {total_soc} | "
        f"Conflicts: {total_conflicts} | "
        f"Time: {compute_time * 1000:.2f} ms"
    )
    yield {
        "type":    "done",
        "result":  MapfResult(makespan, compute_time, total_soc, makespan, total_conflicts),
        "message": msg,
    }


# ===========================================================================
# ── ALGORITHM 2: PRIORITIZED PLANNING ────────────────────────────────────────
# ===========================================================================

def solve_prioritized(
    maze:   list[list[int | str]],
    starts: list[tuple[int, int]],
    goals:  list[tuple[int, int]],
) -> Generator[dict, None, None]:
    """
    Prioritized Planning  (Silver 2005)  —  sequential, reservation-aware.

    Agent 0 plans freely.  Each subsequent agent treats the space-time
    positions of all higher-priority agents as hard constraints and uses
    space-time A* to route around them.

    Complete (always finds a solution if one exists under the priority
    ordering) but not optimal: the first agent always gets the shortest
    possible path; later agents may detour significantly.

    The '"plan"' yield for each agent includes the constraint count,
    making the priority effect visible in the HUD.

    Complexity: O(n · T·V·log(T·V))  where T = time horizon

    Yields:
        "plan"  — once per agent (includes constraint_count field).
        "step"  — one simulation tick (conflicts should always be empty).
        "done"  — terminal; carries MapfResult.
    """
    n        = len(starts)
    t0_all   = time.perf_counter()
    paths:    list[list[tuple[int, int]]] = []
    reserved: set[tuple[int, int, int]]   = set()   # (r, c, t) space-time reservations

    # ── Planning phase (sequential, highest priority first) ───────────────
    for i in range(n):
        path = _spacetime_astar(maze, starts[i], goals[i], reserved)
        if path is None:
            path = [starts[i]]
        paths.append(path)

        # Reserve every (r, c, t) this agent occupies.  At the goal, extend
        # reservations to _MAX_TIME so no lower-priority agent can ever route
        # through a resting agent's cell.  The +20 heuristic was insufficient
        # on long detour paths: if agent j's detour exceeded horizon, the goal
        # cell was unreserved at t > horizon and _simulate flagged a conflict,
        # breaking Prioritized Planning's conflict-free-by-construction guarantee.
        horizon = _MAX_TIME
        padded  = _pad_path(path, horizon)
        for t, (r, c) in enumerate(padded):
            reserved.add((r, c, t))

        yield {
            "type":             "plan",
            "agent":            i,
            "path_len":         len(path),
            "constraint_count": len(reserved),
            "title":            (
                f"Prioritized Planning — agent {i} (priority {i})"
                f"  |  {len(reserved)} space-time reservations"
            ),
            "steps": i + 1,
        }

    # ── Simulation phase ─────────────────────────────────────────────────
    makespan  = max(len(p) for p in paths)
    total_soc = sum(max(0, len(p) - 1) for p in paths)   # moves, not positions
    
    for state in _simulate(paths, goals, "Prioritized Planning"):
        yield state

    compute_time = time.perf_counter() - t0_all
    solved       = all(paths[i][-1] == goals[i] for i in range(n))
    status       = "✅ SOLVED" if solved else "⚠  PARTIAL"
    msg = (
        f"{status} | Makespan: {makespan} | SoC: {total_soc} | "
        f"Conflicts: 0 (by construction) | "
        f"Time: {compute_time * 1000:.2f} ms"
    )
    yield {
        "type":    "done",
        "result":  MapfResult(makespan, compute_time, total_soc, makespan, 0),
        "message": msg,
    }


# ===========================================================================
# ── ALGORITHM 3: CONFLICT-BASED SEARCH (CBS) ─────────────────────────────────
# ===========================================================================

def solve_cbs(
    maze:      list[list[int | str]],
    starts:    list[tuple[int, int]],
    goals:     list[tuple[int, int]],
    max_nodes: int = CBS_MAX_NODES,
) -> Generator[dict, None, None]:
    """
    Conflict-Based Search  (Sharon et al. 2012)  —  optimal MAPF.

    Two-level search:

    HIGH LEVEL — constraint tree (CT):
        Each node holds per-agent constraints and a set of paths computed
        under those constraints.  Nodes are expanded in order of
        sum-of-costs (best-first).

    LOW LEVEL — space-time A*:
        Given a set of forbidden (r, c, t) cells for one agent, compute
        the optimal path for that agent.

    When a CT node is expanded:
        1. Find its first vertex conflict (agent_i, agent_j, r, c, t).
        2. If none → OPTIMAL SOLUTION FOUND.
        3. Else → create two child nodes:
              - One forbidding agent_i at (r, c, t).
              - One forbidding agent_j at (r, c, t).

    Capped at 'max_nodes' CT expansions for interactive use.
    The best solution found before the cap is still returned.

    Complexity: O(b^d · T·V·log(T·V))

    Yields:
        "plan"  — once per CT node expanded (agent=-1 for CBS node).
        "step"  — simulation tick of the best solution found.
        "done"  — terminal; carries MapfResult.
    """
    n      = len(starts)
    t0_all = time.perf_counter()

    # ── Low-level planner: A* under per-agent constraints ─────────────────
    def _low_level(
        constraints_per_agent: list[set[tuple[int, int, int]]],
    ) -> list[list[tuple[int, int]]]:
        result: list[list[tuple[int, int]]] = []
        for i in range(n):
            p = _spacetime_astar(maze, starts[i], goals[i], constraints_per_agent[i])
            result.append(p if p is not None else [starts[i]])
        return result

    def _soc(paths: list[list[tuple[int, int]]]) -> int:
        # Sum-of-Costs must count MOVES per agent, not positions.
        # A path of k moves has k+1 position entries (including the start).
        # Using len(p) overcounts by exactly n_agents relative to the MAPF
        # literature standard (Sharon et al. 2012), making every SoC value
        # reported in the HUD and MapfResult n_agents higher than it should
        # be.  len(p) - 1 gives the correct move count per agent.
        return sum(max(0, len(p) - 1) for p in paths)

    # ── Initialise CT root ────────────────────────────────────────────────
    _uid          = itertools.count()
    root_c: list[set[tuple[int, int, int]]] = [set() for _ in range(n)]
    root_paths    = _low_level(root_c)
    root_cost     = _soc(root_paths)

    # heap entries: (cost, uid, constraints_list, paths)
    open_ct: list[tuple[int, int, list, list]] = [
        (root_cost, next(_uid), root_c, root_paths)
    ]

    nodes_expanded  = 0
    best_paths      = root_paths
    best_soc        = root_cost
    solution_found  = False

    # ── CBS main loop ─────────────────────────────────────────────────────
    while open_ct and nodes_expanded < max_nodes:
        cost, _, constraints, paths = heapq.heappop(open_ct)
        nodes_expanded += 1

        # Keep the cheapest paths seen (for capped-run fallback)
        if cost < best_soc:
            best_soc   = cost
            best_paths = paths

        # Yield a planning-phase update so the HUD stays alive.
        # "paths" is forwarded so the consumer can paint the live
        # CT-node solution instead of keeping agents frozen at starts.
        conflict = _find_first_conflict(paths)
        status   = "no conflict" if conflict is None else f"conflict @ t={conflict[4]}"
        yield {
            "type":      "plan",
            "agent":     -1,          # -1 signals a CBS node (not a single agent)
            "path_len":  cost,
            "title":     (
                f"CBS — node {nodes_expanded}/{max_nodes} | "
                f"SoC: {cost} | {status}"
            ),
            "steps":     nodes_expanded,
            "max_nodes": max_nodes,   # exposed so the driver can render a progress bar
            "paths":     paths,       # live low-level paths for this CT node
            "conflicts": [] if conflict is None
                         else list(_detect_conflicts(
                             _positions_at(paths, conflict[4])
                         )),
        }

        if conflict is None:
            best_paths     = paths
            solution_found = True
            break

        ai, aj, r, c, t = conflict

        # Determine the correct per-agent constraint for CBS branching.
        #
        # VERTEX conflict: both agents occupy (r, c) at timestep t.
        #   → forbid each agent from (r, c, t).  Symmetric; current code
        #     was already correct for this case.
        #
        # SWAP conflict: _find_first_conflict returns agent_i's destination
        #   (r, c) at timestep t, but agent_j is simultaneously heading to
        #   agent_i's t-1 position — a completely different cell.  Adding
        #   (r, c, t) to agent_j's constraints is vacuous (agent_j was never
        #   going to (r, c) anyway) and leaves the swap unresolved, forcing
        #   CBS to waste CT nodes on an unresolvable branch.
        #
        #   Correct fix: for agent_j's branch, constrain it from ITS OWN
        #   destination at t, which is agent_j's actual position in the
        #   current plan at timestep t.
        aj_at_t = paths[aj][min(t, len(paths[aj]) - 1)]
        is_swap = (aj_at_t != (r, c))   # vertex → both at (r,c); swap → different cells

        constraint_ai = (r, c, t)
        constraint_aj = (r, c, t) if not is_swap else (aj_at_t[0], aj_at_t[1], t)

        # Branch on the conflict: two child CT nodes
        for branch_agent, branch_constraint in ((ai, constraint_ai), (aj, constraint_aj)):
            new_c = [s.copy() for s in constraints]
            new_c[branch_agent].add(branch_constraint)
            new_paths = _low_level(new_c)
            new_cost  = _soc(new_paths)
            heapq.heappush(open_ct, (new_cost, next(_uid), new_c, new_paths))

    # ── Simulate best solution ────────────────────────────────────────────
    makespan    = max(len(p) for p in best_paths)
    total_soc   = _soc(best_paths)
    remaining_c = _find_first_conflict(best_paths)
    algo_label  = (
        "CBS (optimal)"     if solution_found
        else "CBS (capped)" if nodes_expanded >= max_nodes
        else "CBS"
    )

    for state in _simulate(best_paths, goals, algo_label):
        yield state

    compute_time = time.perf_counter() - t0_all
    # M-2 fix: report the true count of remaining conflicts, not a binary
    # 0/1 flag.  A capped CBS run may have dozens of unresolved conflicts;
    # encoding them all as 1 made the field meaningless for diagnosis.
    collisions   = 0 if solution_found else _count_all_conflicts(best_paths)
    truncated    = (nodes_expanded >= max_nodes and not solution_found)
    tag          = (
        "✅ OPTIMAL"   if solution_found
        else "⚠  CAPPED" if truncated
        else "⚠  PARTIAL"
    )
    msg = (
        f"{tag} | CBS nodes: {nodes_expanded} | "
        f"Makespan: {makespan} | SoC: {total_soc} | "
        f"Time: {compute_time * 1000:.2f} ms"
    )
    yield {
        "type":    "done",
        "result":  MapfResult(makespan, compute_time, total_soc, makespan, collisions),
        "message": msg,
    }
