"""
algorithms/pursuit.py — generator implementations for the three pursuit strategies.

Each generator yields "step", "replan", "caught", and "done" dicts for the
animation driver in ui/animation.py. No rendering happens here.

All three strategies operate on the same dynamic environment: the target moves
every tick, walls can appear/disappear, and the agent has to react in real-time.
"""
from __future__ import annotations

import heapq
import random
import time
from typing import Generator

from core.grid  import DIRECTIONS, terrain_cost
from core.graph import manhattan_distance as _manhattan
from core.types import PursuitResult

_PASSABLE: frozenset[int | str] = frozenset({0, '~', 'S', 'E'})
_MAX_STEPS: int = 600      # hard cap — prevents infinite loops on random targets


# ===========================================================================
# ── INTERNAL HELPERS ──────────────────────────────────────────────────────────
# ===========================================================================



def _astar(
    maze:        list[list[int | str]],
    start:       tuple[int, int],
    goal:        tuple[int, int],
    extra_walls: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """
    Standard A* with an optional extra-wall overlay.

    Returns the path from start to goal, or [start] if no path exists
    (agent just stays put).
    """
    rows, cols   = len(maze), len(maze[0])
    extra_walls  = extra_walls or set()

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
                    and nb not in extra_walls
                    and nb not in closed):
                ng = g[curr] + terrain_cost(maze[nr][nc])
                if nb not in g or ng < g[nb]:
                    g[nb]      = ng
                    parent[nb] = curr
                    heapq.heappush(pq, (ng + _manhattan(nb, goal), nb))
    return [start]   # no path — agent stays in place


def _move_target(
    maze:        list[list[int | str]],
    target_pos:  tuple[int, int],
    agent_pos:   tuple[int, int],
    prev_dir:    tuple[int, int],
    evasive:     bool = True,
    extra_walls: set[tuple[int, int]] | None = None,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """
    Move the target one step.

    Evasive mode  — prefers moves that maximise distance from the agent,
                    with a small momentum bonus for the previous direction.
    Random mode   — picks uniformly from valid neighbours.

    Returns '(new_position, new_direction)'.
    """
    rows, cols   = len(maze), len(maze[0])
    r, c         = target_pos
    extra_walls  = extra_walls or set()

    valid = [
        (r + dr, c + dc, dr, dc)
        for dr, dc in DIRECTIONS
        if (0 <= r + dr < rows and 0 <= c + dc < cols
            and maze[r + dr][c + dc] in _PASSABLE
            and (r + dr, c + dc) not in extra_walls)
    ]
    if not valid:
        return target_pos, prev_dir   # completely enclosed — stay put

    if not evasive:
        nr, nc, ndr, ndc = random.choice(valid)
        return (nr, nc), (ndr, ndc)

    # ── Smart Mouse: 3-state heuristic ────────────────────────────────────
    dist_to_agent = _manhattan(target_pos, agent_pos)

    def _passable(nr: int, nc: int) -> bool:
        return (0 <= nr < rows and 0 <= nc < cols
                and maze[nr][nc] in _PASSABLE
                and (nr, nc) not in extra_walls)

    # ── STATE 1: WANDER (hunter is far) ───────────────────────────────────
    # Relaxed random walk.  Avoids reversing; weak momentum to prevent
    # frantic oscillation.
    if dist_to_agent > 8:
        reverse_dir  = (-prev_dir[0], -prev_dir[1])
        non_reverse  = [(nr, nc, dr, dc) for nr, nc, dr, dc in valid
                        if (dr, dc) != reverse_dir]
        pool         = non_reverse if non_reverse else valid
        momentum     = [(nr, nc, dr, dc) for nr, nc, dr, dc in pool
                        if (dr, dc) == prev_dir]
        if momentum and random.random() < 0.40:
            nr, nc, ndr, ndc = momentum[0]
        else:
            nr, nc, ndr, ndc = random.choice(pool)
        return (nr, nc), (ndr, ndc)

    # ── STATE 2: FLEE & JUKE (hunter is close) ────────────────────────────
    # Evaluate each neighbour by escape quality — a composite of:
    #   (a) open space reachable from that cell (dead-end avoidance), and
    #   (b) actual BFS step-cost for the HUNTER to reach that cell (safety).
    # Two critical fixes over the naive version:
    #   1. agent_pos is treated as a wall in the escape BFS — the prey cannot
    #      "see through" the hunter and count cells on the far side as escape
    #      space, which previously caused suicidal walks into the hunter.
    #   2. Safety distance uses a real BFS outward from agent_pos rather than
    #      Manhattan, so topologically dangerous cells (far by Euclidean but
    #      close via a corridor) are correctly scored as unsafe.
    BFS_DEPTH    = 6
    W_SPACE      = 1.5    # open-space weight  (dead-end avoidance)
    W_DIST       = 3.0    # hunter-path-distance weight (dominant: survival first)
    REVERSE_PEN  = 50.0   # oscillation suppressor — dwarfs any BFS/dist delta;
                          # prey only reverses when every forward exit is walled.

    reverse_dir  = (-prev_dir[0], -prev_dir[1])
    ar, ac       = agent_pos

    # ── Hard survival filter ──────────────────────────────────────────────
    # Remove the hunter's cell from the candidate pool entirely.  No scoring
    # artifact can ever make "walk into hunter" look attractive.
    safe = [(nr, nc, dr, dc) for nr, nc, dr, dc in valid
            if (nr, nc) != agent_pos]
    pool = safe if safe else valid   # fully cornered: all moves lethal

    # ── Single BFS outward from agent_pos ────────────────────────────────
    # Yields the true step-cost the hunter needs to reach every reachable
    # cell.  One pass; cost amortised across all candidates this tick.
    agent_dist: dict[tuple[int, int], int] = {agent_pos: 0}
    af   = [(ar, ac, 0)]
    ah   = 0
    while ah < len(af):
        cr, cc, d = af[ah]; ah += 1
        if d >= BFS_DEPTH + 2:          # look slightly past escape horizon
            continue
        for ddr, ddc in DIRECTIONS:
            nnr, nnc = cr + ddr, cc + ddc
            nb = (nnr, nnc)
            if nb not in agent_dist and _passable(nnr, nnc):
                agent_dist[nb] = d + 1
                af.append((nnr, nnc, d + 1))

    def _escape_potential(sr: int, sc: int) -> int:
        """
        BFS open-cell count within BFS_DEPTH from (sr, sc).
        agent_pos is pre-seeded into visited so the flood-fill treats the
        hunter as a wall — cells reachable only by passing through the
        hunter are NOT counted as escape space.
        """
        visited: set[tuple[int, int]] = {(sr, sc), agent_pos}
        frontier = [(sr, sc, 0)]
        head     = 0
        while head < len(frontier):
            cr, cc, depth = frontier[head]; head += 1
            if depth >= BFS_DEPTH:
                continue
            for ddr, ddc in DIRECTIONS:
                nnr, nnc = cr + ddr, cc + ddc
                nb = (nnr, nnc)
                if nb not in visited and _passable(nnr, nnc):
                    visited.add(nb)
                    frontier.append((nnr, nnc, depth + 1))
        return len(visited) - 1         # subtract the agent_pos sentinel

    def _flee_score(nr: int, nc: int, dr: int, dc: int) -> float:
        space     = _escape_potential(nr, nc)
        # Real hunter step-cost to reach this cell.  Cells the hunter
        # cannot reach within BFS_DEPTH+2 get the maximum safety bonus.
        real_dist = float(agent_dist.get((nr, nc), BFS_DEPTH + 3))
        penalty   = REVERSE_PEN if (dr, dc) == reverse_dir else 0.0
        return W_SPACE * space + W_DIST * real_dist - penalty

    best             = max(pool, key=lambda x: _flee_score(x[0], x[1], x[2], x[3]))
    nr, nc, ndr, ndc = best
    return (nr, nc), (ndr, ndc)


def _path_blocked(
    path:        list[tuple[int, int]],
    maze:        list[list[int | str]],
    extra_walls: set[tuple[int, int]],
) -> bool:
    """Return True if any cell on 'path' has become impassable."""
    for r, c in path:
        if maze[r][c] not in _PASSABLE or (r, c) in extra_walls:
            return True
    return False


def _predict_intercept(
    target_pos:  tuple[int, int],
    prev_dir:    tuple[int, int],
    lookahead:   int,
    maze:        list[list[int | str]],
    extra_walls: set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """
    Project target's current direction 'lookahead' steps forward,
    stopping when a wall is encountered.  Returns the predicted cell.
    """
    rows, cols   = len(maze), len(maze[0])
    extra_walls  = extra_walls or set()
    r, c         = target_pos
    dr, dc       = prev_dir

    for _ in range(lookahead):
        nr, nc = r + dr, c + dc
        if (0 <= nr < rows and 0 <= nc < cols
                and maze[nr][nc] in _PASSABLE
                and (nr, nc) not in extra_walls):
            r, c = nr, nc
        else:
            break
    return (r, c)


def _build_schedule(
    raw: list[tuple[int, tuple[int, int]]] | None,
) -> dict[int, tuple[int, int]]:
    """Convert the optional wall schedule list into a timestep-keyed dict."""
    return dict(raw) if raw else {}


# ===========================================================================
# ── ALGORITHM 1: NAIVE RECALCULATION ─────────────────────────────────────────
# ===========================================================================

def solve_naive(
    maze:                 list[list[int | str]],
    start:                tuple[int, int],
    target_start:         tuple[int, int],
    evasive:              bool = True,
    extra_walls_schedule: list[tuple[int, tuple[int, int]]] | None = None,
) -> Generator[dict, None, None]:
    """
    Naive Recalculation — full A* replanned on every single tick.

    This is the simplest correct strategy: always compute the optimal
    path to the target's *current* position.  On a static maze it
    behaves identically to running A* once.  On dynamic mazes (moving
    target + walls) it immediately adapts but at full replanning cost.

    The 'replans' count equals 'steps' — every tick is a replan.
    Use this as the baseline to appreciate Dynamic Repair's savings.

        extra_walls_schedule:  '[(timestep, (r, c)), ...]' — walls that
            appear mid-run.  The controller builds this list; the algorithm
            is pure.
    """
    agent_pos    = start
    target_pos   = target_start
    prev_dir: tuple[int, int] = (1, 0)   # target starts moving South
    extra_walls: set[tuple[int, int]] = set()
    schedule     = _build_schedule(extra_walls_schedule)

    steps   = 0
    replans = 0
    t0_all  = time.perf_counter()

    while steps < _MAX_STEPS:
        # Apply any wall that appears this tick
        if steps in schedule:
            extra_walls.add(schedule[steps])

        # Replan — always
        path    = _astar(maze, agent_pos, target_pos, extra_walls)
        replans += 1

        # Advance agent one step
        prev_agent_pos = agent_pos
        if len(path) > 1:
            agent_pos = path[1]

        caught = (agent_pos == target_pos)

        yield {
            "type":        "step",
            "title":       "Naive Recalculation",
            "steps":       steps + 1 if caught else steps,
            "agent_pos":   agent_pos,
            "target_pos":  target_pos,
            "path":        path,
            "replans":     replans,
            "caught":      caught,
            "extra_walls": extra_walls,
        }

        if caught:
            yield {"type": "caught", "steps": steps + 1, "agent_pos": agent_pos,
                   "target_pos": target_pos, "title": "Naive Recalculation",
                   "path": path, "replans": replans, "extra_walls": extra_walls}
            break

        # Move target — then check cross-swap (agent A→B, target B→A)
        prev_target_pos = target_pos
        target_pos, prev_dir = _move_target(
            maze, target_pos, agent_pos, prev_dir, evasive, extra_walls
        )
        if agent_pos == prev_target_pos and target_pos == prev_agent_pos:
            yield {"type": "caught", "steps": steps + 1, "agent_pos": agent_pos,
                   "target_pos": target_pos, "title": "Naive Recalculation",
                   "path": path, "replans": replans, "extra_walls": extra_walls}
            break
        steps += 1

    compute_time = time.perf_counter() - t0_all
    caught_final = (agent_pos == target_pos)
    final_steps  = steps + 1 if caught_final else steps   # catch tick not yet counted
    if caught_final:
        outcome_str = "✅ CAUGHT!"
    elif final_steps >= _MAX_STEPS:
        outcome_str = f"⏱ Step budget exhausted ({_MAX_STEPS} steps)"
    else:
        outcome_str = "❌ Escaped"
    msg = (
        f"{outcome_str} | "
        f"Steps: {final_steps} | Replans: {replans} (every tick) | "
        f"Time: {compute_time * 1000:.2f} ms"
    )
    yield {
        "type":    "done",
        "result":  PursuitResult(final_steps, compute_time, caught_final, replans),
        "message": msg,
    }


# ===========================================================================
# ── ALGORITHM 2: DYNAMIC REPAIR ──────────────────────────────────────────────
# ===========================================================================

def solve_dynamic_repair(
    maze:                 list[list[int | str]],
    start:                tuple[int, int],
    target_start:         tuple[int, int],
    evasive:              bool = True,
    extra_walls_schedule: list[tuple[int, tuple[int, int]]] | None = None,
    repair_threshold:     int  = 3,
) -> Generator[dict, None, None]:
    """
    Dynamic Repair  (D* Lite inspired)  —  cache-and-repair strategy.

    Core idea: the previous plan is usually still valid.  Only replan when
    the environment has actually changed enough to invalidate it:

        Trigger A: target has drifted more than 'repair_threshold' cells
                   from the path's current goal endpoint.
        Trigger B: a newly-added wall now blocks a cell on the cached path.

    This models the key insight of D* Lite (Koenig & Likhachev 2002):
    rather than recomputing from scratch, identify changed edges and
    propagate only the necessary cost updates — reducing total computation
    from O(steps · (V+E)logV) to O(repairs · (V+E)logV) where
    repairs << steps on slowly-changing environments.

    The 'replans / steps' ratio in the report card is the primary metric:
    a ratio near 1.0 → behaves like Naive; ratio near 0 → the cache is
    reused almost every tick.

        repair_threshold: drift distance (Manhattan) that triggers replan.
    """
    agent_pos    = start
    target_pos   = target_start
    prev_dir: tuple[int, int] = (1, 0)
    extra_walls: set[tuple[int, int]] = set()
    schedule     = _build_schedule(extra_walls_schedule)

    # Initial plan — counted as replan #1 and emitted as a visible "replan"
    # event so the student sees it on the HUD.  Previously this A* call was
    # silent: replans was set to 1 before the loop but no "replan" yield was
    # ever emitted for it, making the first replan count appear from nowhere.
    replans       = 0
    steps         = 0
    t0_all        = time.perf_counter()

    path          = _astar(maze, agent_pos, target_pos, extra_walls)
    cached_goal   = target_pos
    replans      += 1
    yield {
        "type":        "replan",
        "title":       "Dynamic Repair — initial plan (t=0)",
        "steps":       steps,
        "agent_pos":   agent_pos,
        "target_pos":  target_pos,
        "path":        path,
        "replans":     replans,
        "caught":      False,
        "extra_walls": extra_walls,
    }

    while steps < _MAX_STEPS:
        if steps in schedule:
            extra_walls.add(schedule[steps])

        # ── Repair decision ───────────────────────────────────────────────
        drift         = _manhattan(target_pos, cached_goal)
        blocked       = _path_blocked(path, maze, extra_walls)
        need_replan   = (drift > repair_threshold) or blocked or (len(path) <= 1)

        if need_replan:
            path        = _astar(maze, agent_pos, target_pos, extra_walls)
            cached_goal = target_pos
            replans    += 1
            yield {
                "type":        "replan",
                "title":       f"Dynamic Repair — replanning (drift={drift}, blocked={blocked})",
                "steps":       steps,
                "agent_pos":   agent_pos,
                "target_pos":  target_pos,
                "path":        path,
                "replans":     replans,
                "caught":      False,
                "extra_walls": extra_walls,
            }

        # ── Move agent ───────────────────────────────────────────────────
        prev_agent_pos = agent_pos
        if len(path) > 1:
            agent_pos = path[1]
            path      = path[1:]   # consume the step from the cached path

        caught = (agent_pos == target_pos)

        yield {
            "type":        "step",
            "title":       "Dynamic Repair",
            "steps":       steps + 1 if caught else steps,
            "agent_pos":   agent_pos,
            "target_pos":  target_pos,
            "path":        path,
            "replans":     replans,
            "caught":      caught,
            "extra_walls": extra_walls,
        }

        if caught:
            yield {"type": "caught", "steps": steps + 1, "agent_pos": agent_pos,
                   "target_pos": target_pos, "title": "Dynamic Repair",
                   "path": path, "replans": replans, "extra_walls": extra_walls}
            break

        # Move target — then check cross-swap (agent A→B, target B→A)
        prev_target_pos = target_pos
        target_pos, prev_dir = _move_target(
            maze, target_pos, agent_pos, prev_dir, evasive, extra_walls
        )
        if agent_pos == prev_target_pos and target_pos == prev_agent_pos:
            yield {"type": "caught", "steps": steps + 1, "agent_pos": agent_pos,
                   "target_pos": target_pos, "title": "Dynamic Repair",
                   "path": path, "replans": replans, "extra_walls": extra_walls}
            break
        steps += 1

    compute_time  = time.perf_counter() - t0_all
    caught_final  = (agent_pos == target_pos)
    final_steps   = steps + 1 if caught_final else steps   # catch tick not yet counted
    saved         = max(0, final_steps - replans)
    msg = (
        f"{'✅ CAUGHT!' if caught_final else '❌ Escaped'} | "
        f"Steps: {final_steps} | Replans: {replans} (saved ≈{saved} recalcs) | "
        f"Time: {compute_time * 1000:.2f} ms"
    )
    yield {
        "type":    "done",
        "result":  PursuitResult(final_steps, compute_time, caught_final, replans),
        "message": msg,
    }


# ===========================================================================
# ── ALGORITHM 3: GREEDY INTERCEPT ────────────────────────────────────────────
# ===========================================================================

def solve_greedy_intercept(
    maze:                 list[list[int | str]],
    start:                tuple[int, int],
    target_start:         tuple[int, int],
    evasive:              bool = True,
    extra_walls_schedule: list[tuple[int, tuple[int, int]]] | None = None,
    lookahead:            int  = 5,
) -> Generator[dict, None, None]:
    """
    Greedy Intercept — velocity-projection pursuit.

    Instead of chasing where the target IS, this strategy predicts where
    the target will BE in 'lookahead' ticks by projecting its current
    movement direction forward.  The agent then runs A* toward that
    predicted intercept point.

    On a directional evader moving in a straight corridor, the agent can
    cut diagonally to the exit of the corridor and "wait" for the target —
    catching it with far fewer steps than pure pursuit.

    On a random or rapidly-turning target, the prediction is inaccurate and
    the algorithm naturally degrades toward Naive (still correct, just less
    efficient than on directional targets).

    The "intercept" field in every yield allows the animator to render the
    predicted cell with a distinctive colour so students can visually see
    how the prediction tracks the target.

        lookahead:  How many steps ahead to project the target's velocity.
                    Larger values cut further ahead; may overshoot on zigzag
                    evaders.
    """
    agent_pos    = start
    target_pos   = target_start
    prev_dir: tuple[int, int] = (1, 0)
    extra_walls: set[tuple[int, int]] = set()
    schedule     = _build_schedule(extra_walls_schedule)

    # Compute initial intercept and path — emitted as a visible "replan"
    # event (replan #1) so the student can see the algorithm's first
    # prediction on the HUD.  Previously this was silent: replans=1 was set
    # before the loop with no corresponding yield, causing the count to jump
    # from 0 to 1 with no visual trigger that the student could observe.
    replans   = 0
    steps     = 0
    t0_all    = time.perf_counter()

    intercept = _predict_intercept(target_pos, prev_dir, lookahead, maze, extra_walls)
    path      = _astar(maze, agent_pos, intercept, extra_walls)
    if len(path) < 2:
        path = _astar(maze, agent_pos, target_pos, extra_walls)
    replans  += 1
    yield {
        "type":        "replan",
        "title":       f"Greedy Intercept — initial plan, aiming at {intercept}",
        "steps":       steps,
        "agent_pos":   agent_pos,
        "target_pos":  target_pos,
        "intercept":   intercept,
        "path":        path,
        "replans":     replans,
        "caught":      False,
        "extra_walls": extra_walls,
    }

    while steps < _MAX_STEPS:
        if steps in schedule:
            extra_walls.add(schedule[steps])

        # ── Recompute intercept every tick (cheap projection) ─────────────
        # Adjacency override: when the prey is exactly 1 step away the
        # lookahead projection overshoots — it aims 'lookahead' cells past
        # the prey, causing the hunter to step in the wrong direction and
        # miss a trivial kill.  Force the intercept to the prey's current
        # cell so the replan produces a 1-step path straight onto it.
        # This also eliminates the ghost-swap window: the agent can't
        # overshoot into a cell-swap if it steps directly onto the prey.
        if _manhattan(agent_pos, target_pos) == 1:
            new_intercept = target_pos
        else:
            new_intercept = _predict_intercept(
                target_pos, prev_dir, lookahead, maze, extra_walls
            )

        # Replan only when the intercept or path has changed significantly
        blocked       = _path_blocked(path, maze, extra_walls)
        drift         = _manhattan(new_intercept, intercept)
        need_replan   = (drift > 1) or blocked or (len(path) <= 1)

        intercept = new_intercept

        if need_replan:
            new_path = _astar(maze, agent_pos, intercept, extra_walls)
            if len(new_path) < 2:
                new_path = _astar(maze, agent_pos, target_pos, extra_walls)
            path    = new_path
            replans += 1
            yield {
                "type":        "replan",
                "title":       f"Greedy Intercept — aiming at {intercept}",
                "steps":       steps,
                "agent_pos":   agent_pos,
                "target_pos":  target_pos,
                "intercept":   intercept,
                "path":        path,
                "replans":     replans,
                "caught":      False,
                "extra_walls": extra_walls,
            }

        # ── Move agent ───────────────────────────────────────────────────
        prev_agent_pos = agent_pos
        if len(path) > 1:
            agent_pos = path[1]
            path      = path[1:]

        caught = (agent_pos == target_pos)

        yield {
            "type":        "step",
            "title":       "Greedy Intercept",
            "steps":       steps + 1 if caught else steps,
            "agent_pos":   agent_pos,
            "target_pos":  target_pos,
            "intercept":   intercept,
            "path":        path,
            "replans":     replans,
            "caught":      caught,
            "extra_walls": extra_walls,
        }

        if caught:
            yield {"type": "caught", "steps": steps + 1, "agent_pos": agent_pos,
                   "target_pos": target_pos, "title": "Greedy Intercept",
                   "path": path, "replans": replans, "extra_walls": extra_walls,
                   "intercept": intercept}
            break

        # Move target — then check cross-swap (agent A→B, target B→A)
        prev_target_pos = target_pos
        target_pos, prev_dir = _move_target(
            maze, target_pos, agent_pos, prev_dir, evasive, extra_walls
        )
        if agent_pos == prev_target_pos and target_pos == prev_agent_pos:
            yield {"type": "caught", "steps": steps + 1, "agent_pos": agent_pos,
                   "target_pos": target_pos, "title": "Greedy Intercept",
                   "path": path, "replans": replans, "extra_walls": extra_walls,
                   "intercept": intercept}
            break
        steps += 1

    compute_time  = time.perf_counter() - t0_all
    caught_final  = (agent_pos == target_pos)
    final_steps   = steps + 1 if caught_final else steps   # catch tick not yet counted
    msg = (
        f"{'✅ CAUGHT!' if caught_final else '❌ Escaped'} | "
        f"Steps: {final_steps} | Intercept replans: {replans} | "
        f"Lookahead: {lookahead} | "
        f"Time: {compute_time * 1000:.2f} ms"
    )
    yield {
        "type":    "done",
        "result":  PursuitResult(final_steps, compute_time, caught_final, replans),
        "message": msg,
    }
