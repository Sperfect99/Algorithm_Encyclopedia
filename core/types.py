"""
core/types.py — result types returned by all four solver modules.

NamedTuples so they're immutable and easy to compare.
Using float for steps/cost means I can use float('inf') for failures
instead of adding a separate 'succeeded' bool to every type.
"""
from __future__ import annotations

from typing import NamedTuple


class RunResult(NamedTuple):
    """Result from a single-agent pathfinding run (classic maze module)."""
    steps:        float  # nodes expanded — float so we can use inf for failure
    compute_time: float  # pure algorithm time in seconds (UI overhead stripped)
    path_len:     int    # cells in the solution path (0 on failure)
    path_cost:    int    # weighted terrain cost of solution (0 on failure)


class _StepRecord(NamedTuple):
    """One frame delta captured by the autopsy recorder.

    Stores both the before and after cell value so the autopsy replayer
    can move forward AND backward through a recorded run.
    """
    r:         int        # row of the mutated cell
    c:         int        # column of the mutated cell
    prev_cell: int | str  # maze[r][c] value BEFORE the mutation
    new_cell:  int | str  # maze[r][c] value AFTER the mutation
    hud:       str        # HUD text at the time of this step


class MapfResult(NamedTuple):
    """Result from a multi-agent pathfinding run.

    collisions means different things per algorithm:
      - Independent A*: total vertex conflicts during simulation (can be large)
      - Prioritized Planning: always 0 (reservations prevent conflicts)
      - CBS solved: always 0 (search only terminates on conflict-free solution)
      - CBS capped (hit node budget): actual remaining conflicts in best partial solution
    """
    timesteps:    int    # simulation ticks until last agent reaches goal
    compute_time: float  # pure algorithm time in seconds
    sum_of_costs: int    # sum of individual path lengths minus 1 per agent (CBS metric)
    makespan:     int    # ticks until every agent reaches its goal
    collisions:   int    # vertex conflicts detected (0 = conflict-free)


class PursuitResult(NamedTuple):
    """Result from a dynamic pursuit / Pac-Man run.

    replans is the key metric for comparing strategies:
    Naive replans every single tick; Dynamic Repair only replans when needed.
    Divide replans / steps to get the replan frequency.
    """
    steps:        int    # total movement steps taken
    compute_time: float  # pure algorithm time in seconds
    caught:       bool   # True if agent reached the target within the step budget
    replans:      int    # number of path recalculations


class TreasureRunResult(NamedTuple):
    """Result from a TSP / Treasure Hunt run.

    Two competing metrics:
      total_steps   — hop count for the full tour (what you see animated)
      tour_cost     — weighted terrain cost (what GA and Brute Force actually optimise)

    They're equal when there's no mud terrain. With mud they diverge, which is
    kind of the whole point of showing both.
    """
    total_steps:   float             # cells walked across the whole journey (inf = failed)
    compute_time:  float             # pure algorithm time in seconds
    tour_cost:     int               # weighted terrain cost (mud=3, road=1)
    time_to_first: int               # steps before the first treasure is collected
    tour_order:    tuple[int, ...]   # sequence of treasure indices visited
    n_collected:   int               # treasures collected (== n_treasures on success)
    n_treasures:   int               # total treasures on the map
