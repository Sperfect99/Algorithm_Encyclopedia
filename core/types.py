"""
core/types.py
-------------
Canonical result and record types for the Algorithm Encyclopedia.

All types are immutable NamedTuples — zero dependencies, instantly
serialisable, and safe to use as dict keys or in multiprocessing contexts.

Phase 1 exports (classic pathfinding):
    RunResult         — single-agent pathfinding result (15 classic algorithms)
    _StepRecord       — single animation-frame delta (autopsy recording)

Phase 3 exports (MAPF + pursuit):
    MapfResult        — multi-agent pathfinding result
    PursuitResult     — dynamic pursuit / interception result

Phase 4 exports (TSP / Treasure Hunt):
    TreasureRunResult — TSP algorithm result (all three TSP solvers)
"""
from __future__ import annotations

from typing import NamedTuple


# ===========================================================================
# ── PHASE 1: CLASSIC PATHFINDING ─────────────────────────────────────────────
# ===========================================================================

class RunResult(NamedTuple):
    """
    Result from a single-agent pathfinding run.

    ``steps`` uses float so ``float('inf')`` can signal a failed run without
    a separate bool field — callers test ``result.steps == float('inf')``.
    """
    steps:        float  # nodes expanded  (float → allows inf for failure)
    compute_time: float  # pure algorithm wall-time in seconds (UI stripped)
    path_len:     int    # solution-path cell count  (0 on failure)
    path_cost:    int    # weighted terrain cost of solution  (0 on failure)


class _StepRecord(NamedTuple):
    """One animation-frame delta captured by the autopsy recorder.

    The autopsy replayer applies new_cell forward and prev_cell
    backward, so both directions of navigation are fully reversible.
    extra carries algorithm-specific data (g/h/f scores, queue depth,
    direction, etc.) for the step-by-step explainer. None when
    the recording predates the explainer or the algorithm has no
    numeric state worth showing.
    """
    r:          int         # row of the mutated cell
    c:          int         # column of the mutated cell
    prev_cell:  int | str   # maze[r][c] value BEFORE the mutation
    new_cell:   int | str   # maze[r][c] value AFTER the mutation
    hud:        str         # HUD text at the time of mutation
    extra:      dict | None = None  # explainer payload — see maze_views._explain_step


# ===========================================================================
# ── PHASE 3: MULTI-AGENT PATHFINDING (MAPF) ──────────────────────────────────
# ===========================================================================

class MapfResult(NamedTuple):
    """
    Result from a multi-agent pathfinding run.

    Metrics follow the standard MAPF literature:

    ``timesteps``
        Number of simulation ticks until the last agent reaches its goal
        (identical to ``makespan`` for the solved case).

    ``sum_of_costs`` (SoC)
        Sum of individual move counts (path length − 1 per agent).  The
        primary optimality criterion for CBS (Sharon et al. 2012).
        Lower is better; always ≥ makespan for n_agents = 1.

    ``makespan``
        Timesteps until every agent has reached its goal.  Equal to the
        length of the longest individual path.

    ``collisions``
        Conflict count with algorithm-dependent semantics:

        Independent A*: total vertex conflicts observed during
        simulation — can be large on dense maps.

        Prioritized Planning: always 0 by construction (space-time
        reservations prevent conflicts before simulation).

        CBS solved run: always 0 by construction (the CT search
        terminates only when a conflict-free solution is proven).

        CBS capped run (nodes_expanded >= max_nodes before convergence):
        the true count of remaining vertex and edge (swap) conflicts in
        the best partial solution found so far. May be > 1.

        Students comparing Independent A* vs CBS should read this as
        "how many conflicts are still present in the displayed paths?"
        Zero always means conflict-free; any positive value means
        agents will collide.
    """
    timesteps:    int    # simulation ticks to completion
    compute_time: float  # pure algorithm wall-time in seconds
    sum_of_costs: int    # sum of individual move counts (CBS metric; len(path)-1 per agent)
    makespan:     int    # ticks until last agent reaches goal (== timesteps)
    collisions:   int    # vertex conflicts detected (0 = conflict-free)


# ===========================================================================
# ── PHASE 3: DYNAMIC PURSUIT (PAC-MAN MODE) ──────────────────────────────────
# ===========================================================================

class PursuitResult(NamedTuple):
    """
    Result from a dynamic pursuit / interception run.

    ``caught``
        True if the agent reached the target's cell within the step budget.

    ``replans``
        Number of times the path was recalculated.  Divide by ``steps`` to
        get the replanning frequency — the key metric for comparing Naive
        (replans every tick) vs. Dynamic Repair (replans only on change).
    """
    steps:        int    # total agent movement steps taken
    compute_time: float  # pure algorithm wall-time in seconds
    caught:       bool   # True → agent reached target within budget
    replans:      int    # path recalculations (Naive = steps; Repair << steps)


# ===========================================================================
# ── PHASE 4: TSP / TREASURE HUNT ─────────────────────────────────────────────
# ===========================================================================

class TreasureRunResult(NamedTuple):
    """
    Result from a single TSP algorithm run on a treasure-hunt maze.

    Encapsulates the two competing pedagogical metrics at the core of the
    Treasure Hunt domain:

    ``total_steps``
        Total cells walked across the ENTIRE journey — the primary
        tour-optimality metric.  ``float('inf')`` signals a failed run
        (unreachable treasure or N > 8 for Brute Force).

    ``time_to_first``
        Cells walked before the FIRST treasure is collected.  The urgency
        metric.  Nearest Neighbour always minimises this; Brute Force and
        GA may sacrifice it for a shorter total tour.

    ``tour_cost``
        Weighted terrain cost of the tour (mud cells cost 3, road costs 1).
        Equals ``total_steps`` when terrain is disabled.  This is what the
        algorithms actually optimise (cost_matrix is terrain-aware).

    ``tour_order``
        The sequence of treasure indices visited, e.g. [3, 1, 2] means the
        agent visited T3 first, then T1, then T2.  Used to render the route
        string "S → T3 → T1 → T2" in the Report Card and Duel overlay.

    ``n_collected``
        Treasures successfully collected.  Always equals ``n_treasures`` on
        a successful run; less than it on a failure.

    ``n_treasures``
        Total treasures on the map (N).  Stored here so Report Cards and
        Benchmark tables can display "N/N ✅" without needing the points
        list to still be in scope.
    """
    total_steps:   float             # total cells walked  (float → allows inf)
    compute_time:  float             # pure algorithm wall-time in seconds
    tour_cost:     int               # weighted terrain cost  (mud=3, road=1)
    time_to_first: int               # steps before first treasure collected
    tour_order:    tuple[int, ...]   # sequence of treasure indices visited (immutable)
    n_collected:   int               # treasures collected (== n_treasures on success)
    n_treasures:   int               # total treasures on the map