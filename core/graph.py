"""
core/graph.py — distance calculations and path utilities.

Shared across all solver modules. No side effects.
"""
from __future__ import annotations

import collections
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.types import RunResult


def manhattan_distance(p1: tuple[int, int], p2: tuple[int, int]) -> int:
    """Manhattan distance between two grid positions.

    Used as the A* / Greedy heuristic. Admissible on this grid because
    the minimum step cost is 1, so it never overestimates.
    """
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


# Short alias used in multi_agent_solver
manhattan = manhattan_distance


def validate_yield(state: object, algo_name: str = "") -> str | None:
    """Check that one yielded dict from an algorithm generator is well-formed.

    The generator contract has four valid event types:

      step        — a cell was explored. Required keys: type, r, c, steps,
                    title, restore.  r and c must be ints.
      render      — a full-frame redraw (used by Bellman-Ford and similar).
                    Required keys: type, steps, message.
      record_only — autopsy capture without rendering (Bellman-Ford,
                    Dead-End Filling). Required keys: type, r, c, prev, new.
                    The animation loop records these but does not draw them.
      done        — algorithm finished. Required keys: type, result.
                    result must be a RunResult.

    Returns None when the dict is valid, or a short description when not.
    This is called in smoke_tests for every yielded state so that a new
    algorithm with a missing key is caught immediately on the first CI run.
    """
    if not isinstance(state, dict):
        return (f"{algo_name}: yielded {type(state).__name__}, "
                f"expected dict")

    t = state.get("type")
    if t not in {"step", "render", "done", "record_only"}:
        return (f"{algo_name}: unknown yield type {t!r} "
                f"(expected 'step', 'render', 'record_only', or 'done')")

    if t == "step":
        for key in ("r", "c", "steps", "title", "restore"):
            if key not in state:
                return f"{algo_name}: step dict missing required key '{key}'"
        if not isinstance(state["r"], int):
            return (f"{algo_name}: step['r'] must be int, "
                    f"got {type(state['r']).__name__}")
        if not isinstance(state["c"], int):
            return (f"{algo_name}: step['c'] must be int, "
                    f"got {type(state['c']).__name__}")
        if not isinstance(state["steps"], int):
            return (f"{algo_name}: step['steps'] must be int, "
                    f"got {type(state['steps']).__name__}")

    elif t == "render":
        for key in ("steps", "message"):
            if key not in state:
                return f"{algo_name}: render dict missing required key '{key}'"

    elif t == "record_only":
        for key in ("r", "c", "prev", "new"):
            if key not in state:
                return f"{algo_name}: record_only dict missing required key '{key}'"

    elif t == "done":
        if "result" not in state:
            return f"{algo_name}: done dict missing required key 'result'"
        # import here to avoid a circular import at module level
        from core.types import RunResult
        if not isinstance(state["result"], RunResult):
            return (f"{algo_name}: done['result'] must be RunResult, "
                    f"got {type(state['result']).__name__}")

    return None


def validate_path(
    maze:       list[list[int | str]],
    path_len:   int,
    path_cost:  int,
) -> str | None:
    """Check that the path the algorithm stamped on the maze is physically valid.

    reconstruct_path_cells marks every intermediate cell as 'P'. S and E keep
    their original markers. path_len counts those 'P' cells — S and E not
    included.

    Returns None when everything looks right, or a short description of what
    went wrong.

    A full BFS through 'P' cells is unreliable here because the animation loop
    leaves explored-but-discarded cells as '.' — the same value that some path
    cells temporarily hold before the reconstruction pass. Instead we check three
    things that are robust against whatever state the animation left the maze in:

      1. Count of 'P' cells == path_len.
      2. S has at least one 'P' or 'E' neighbour — path leaves the start.
      3. E has at least one 'P' or 'S' neighbour — path arrives at the end.
    """
    if path_len == 0:
        return None  # no path claimed — nothing to check

    rows, cols = len(maze), len(maze[0])
    dirs       = [(-1, 0), (0, 1), (1, 0), (0, -1)]

    start = end = None
    for r in range(rows):
        for c in range(cols):
            v = maze[r][c]
            if v == 'S':
                start = (r, c)
            elif v == 'E':
                end = (r, c)

    if start is None:
        return "S not found in maze"
    if end is None:
        return "E not found in maze"

    # Count 'P' cells — must match what the algorithm reported
    p_cells = sum(1 for r in range(rows) for c in range(cols) if maze[r][c] == 'P')
    if p_cells != path_len:
        return f"P-cell count {p_cells} ≠ reported path_len {path_len}"

    # Terrain costs at least 1 per cell
    if path_cost < path_len:
        return (f"path_cost {path_cost} < path_len {path_len} "
                f"— impossible unless terrain_cost is broken")

    def _adj(pos: tuple[int, int]) -> list[int | str]:
        r, c = pos
        return [
            maze[r + dr][c + dc]
            for dr, dc in dirs
            if 0 <= r + dr < rows and 0 <= c + dc < cols
        ]

    if 'P' not in _adj(start) and 'E' not in _adj(start):
        return "no P cell adjacent to S — path does not leave the start"

    if 'P' not in _adj(end) and 'S' not in _adj(end):
        return "no P cell adjacent to E — path does not reach the end"

    return None


def validate_tsp_result(
    total_steps:  float,
    tour_cost:    int,
    n_collected:  int,
    n_treasures:  int,
    tour_order:   tuple,
) -> str | None:
    """Sanity-check a TreasureRunResult after a TSP run.

    Returns None when everything looks right, or a short description of
    what went wrong. Called in treasure_solver2 after show_report_card.
    """
    import math
    if math.isinf(total_steps):
        return None  # algorithm didn't finish — nothing to check

    if n_collected != n_treasures:
        return (f"collected {n_collected} of {n_treasures} treasures "
                f"— tour did not visit every point")

    if tour_cost <= 0:
        return f"tour_cost {tour_cost} ≤ 0 — impossible on a non-empty tour"

    if len(tour_order) != n_treasures:
        return (f"tour_order has {len(tour_order)} entries "
                f"but map has {n_treasures} treasures")

    return None


def validate_mapf_result(
    makespan:     int,
    sum_of_costs: int,
    collisions:   int,
    n_agents:     int,
) -> str | None:
    """Sanity-check a MapfResult after a MAPF run.

    Returns None when everything looks right, or a short description of
    what went wrong. Called in multi_agent_solver after show_report_card.
    """
    if makespan <= 0:
        return None  # no solution found — nothing to check

    if sum_of_costs < n_agents:
        return (f"sum_of_costs {sum_of_costs} < n_agents {n_agents} "
                f"— every agent needs at least 1 step")

    if collisions < 0:
        return f"collisions {collisions} < 0 — counter corrupted"

    return None


def validate_pursuit_result(
    steps:   int,
    replans: int,
    caught:  bool,
) -> str | None:
    """Sanity-check a PursuitResult after a Pursuit-Evasion run.

    Returns None when everything looks right, or a short description of
    what went wrong. Called in dynamic_solver3 after show_report_card.
    """
    if steps <= 0:
        return None  # no movement recorded — nothing to check

    if replans < 0:
        return f"replans {replans} < 0 — counter corrupted"

    if caught and replans > steps:
        return (f"replans {replans} > steps {steps} "
                f"— cannot replan more times than there are steps")

    return None


def _deduplicate_path(
    history: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Remove loops from a traversal history in O(n) time.

    When the agent visits a cell it's already been to, everything between
    the two visits is a loop — we cut it out. This repeats until there are
    no more loops, giving a physically walkable path with no teleportation.

    Example:
        history = [S, A, B, C, A, D, E]   # agent looped A → B → C → A
        result  = [S, A, D, E]             # loop B → C removed at re-entry of A

    Important: the naive "keep first occurrence" approach produces [S, A, B, C, D, E]
    which has a C→D teleportation gap (they're not adjacent). Loop-truncation is
    the correct fix.
    """
    path:     list[tuple[int, int]]       = []
    seen_idx: dict[tuple[int, int], int]  = {}

    for pos in history:
        if pos in seen_idx:
            idx = seen_idx[pos]
            # Remove everything after the first visit to this cell
            for removed in path[idx + 1:]:
                del seen_idx[removed]
            path = path[:idx + 1]
        else:
            seen_idx[pos] = len(path)
            path.append(pos)

    return path