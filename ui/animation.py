"""
ui/animation.py — bridges algorithm generators and the terminal.

All timing (time.sleep / precise_sleep) lives here.
Generators in algorithms/ know nothing about the UI; this module drives them
and handles every yield type they can emit.
"""

from __future__ import annotations

import time
from typing import Generator

from core.types import RunResult, MapfResult, PursuitResult, TreasureRunResult, _StepRecord
from ui.theme   import (
    C_BIGO, C_PQ, C_CONFLICT, C_TARGET, C_INTERCEPT,
    C_HEAD, C_PATH, C_END,
    C_TREASURE, C_GA_LIVE, C_STAT, C_DIM,
)
from ui.renderer import (
    render, render_mapf, render_pursuit, CELL_RENDER,
    render_tsp, render_tsp_ga_overlay,
)
from ui.terminal_utils import (
    hide_cursor, show_cursor, precise_sleep, PROGRESS_BAR_WIDTH,
)


# Hard cap on autopsy recording — prevents OOM on algos like Random Mouse
# that can take tens of thousands of steps. 50k frames is already ~10-15 MB.
# The run itself continues; autopsy is just truncated silently.
_AUTOPSY_MAX_FRAMES: int = 50_000

# Anything >= this is treated as "instant mode" (no animation, no recording).
_BENCH_SKIP: int = 999_999

# ── MAPF timing ───────────────────────────────────────────────────────────────
# Extra pause on conflict frames — without this the flash is too brief to notice
_MAPF_CONFLICT_FLASH_DELAY: float = 0.25

# How long the "CBS finished planning → now simulating" banner stays on screen
_CBS_TRANSITION_HOLD: float = 0.6

# Cap per-frame sleep during CBS planning so a long plan doesn't freeze the UI
# for an uncomfortable amount of time
_CBS_PLAN_FRAME_MAX_SLEEP: float = 0.3

# Fallback node budget for CBS if the generator doesn't include "max_nodes"
# in a "plan" yield. Should match CBS_MAX_NODES in algorithms/mapf.py.
_CBS_MAX_NODES_FALLBACK: int = 500

# ── Pursuit timing ────────────────────────────────────────────────────────────
_PURSUIT_REPLAN_FLASH_DELAY: float = 0.15  # brief pause so the replan is visible
_PURSUIT_CAUGHT_HOLD:        float = 0.4   # hold the "CAUGHT" moment a bit longer

# ── TSP timing ────────────────────────────────────────────────────────────────
_TSP_BF_DISABLED_HOLD: float = 2.5  # time to read the "N > 8, too slow" warning
_TSP_ANNOUNCE_HOLD:    float = 0.9  # pause before animating the found tour
_TSP_POLISH_HOLD:      float = 0.3  # pause on the "2-opt polishing" status



# --- run_algorithm() — Phase 1 driver for all 15 classic pathfinding algos ---

def run_algorithm(
    gen:                Generator[dict, None, None],
    maze:               list[list[int | str]],
    skip_frames:        int,
    delay:              float,
    algo_name:          str,
    active_complexity:  list[str],
    active_recording:   list[_StepRecord] | None,
    fog:                set[tuple[int, int]] | None = None,
) -> RunResult:
    """Drive a classic pathfinding generator to completion.

    Handles yield types: "step", "render", "record_only", "done".
    """
    hide_cursor()
    try:
        for state in gen:
            stype = state["type"]

            if stype == "step":
                r       = state["r"]
                c       = state["c"]
                steps   = state["steps"]
                title   = state["title"]
                restore = state.get("restore", ".")
                pq_info = state.get("pq_info", "")

                original    = maze[r][c]
                is_endpoint = original in {'S', 'E'}

                if not is_endpoint:
                    maze[r][c] = '@'

                if steps % skip_frames == 0:
                    hud_lines = [f"Running: {title} | Steps: {steps}"]
                    if active_complexity[0]:
                        hud_lines.append(
                            f"  {C_BIGO}📐 {active_complexity[0]}{C_END}"
                        )
                    if pq_info and skip_frames < _BENCH_SKIP:
                        hud_lines.append(
                            f"  {C_PQ}🗂  PQ top: {pq_info}"
                            f"  {C_DIM}(g=path cost  h=manhattan  f=g+h){C_END}"
                        )
                    render(maze, "\n".join(hud_lines), fog=fog)
                    if delay > 0:
                        precise_sleep(delay)

                if not is_endpoint:
                    # Preserve mud cells — don't overwrite '~' with '.' on restore.
                    # A bit tricky: restore value comes from the generator, but we
                    # always want mud to stay mud so the terrain stays visible.
                    actual_restore: int | str = (
                        original if (original == '~' and restore == '.') else restore
                    )
                    if active_recording is not None and len(active_recording) < _AUTOPSY_MAX_FRAMES:
                        active_recording.append(_StepRecord(
                            r, c, original, actual_restore,
                            f"Running: {title} | Steps: {steps}",
                        ))
                    maze[r][c] = actual_restore

            elif stype == "render":
                steps   = state["steps"]
                message = state.get("message", "")
                if steps % skip_frames == 0:
                    render(maze, message, fog=fog)
                    if delay > 0:
                        precise_sleep(delay)

            elif stype == "record_only":
                # Some algos (Bellman-Ford) emit these for autopsy without
                # actually rendering — just capture the delta and move on
                if active_recording is not None and len(active_recording) < _AUTOPSY_MAX_FRAMES:
                    active_recording.append(_StepRecord(
                        r=state["r"],
                        c=state["c"],
                        prev_cell=state["prev"],
                        new_cell=state["new"],
                        hud=state["hud"],
                    ))

            elif stype == "done":
                result:  RunResult = state["result"]
                message: str       = state.get("message", "")
                render(maze, message, fog=fog)
                return result

        # Should only hit this if the generator exits without a "done" yield
        return RunResult(float('inf'), 0.0, 0, 0)
    finally:
        gen.close()
        show_cursor()



# --- animate_step() — single-step tick used by Race/Duel/Benchmark ---

def animate_step(
    maze:              list[list[int | str]],
    r:                 int,
    c:                 int,
    steps:             int,
    skip_frames:       int,
    delay:             float,
    title:             str,
    restore_value:     int | str = '.',
    fog:               set[tuple[int, int]] | None = None,
    visit_count:       dict[tuple[int, int], int]  | None = None,
    pq_info:           str = "",
    active_complexity: list[str] | None = None,
    active_recording:  list[_StepRecord] | None = None,
) -> None:
    """Single-step tick for Race/Duel/Benchmark — kept separate from the
    generator-based run_algorithm() because those modes drive animation
    from pre-recorded step lists rather than live generators."""
    original    = maze[r][c]
    is_endpoint = original in {'S', 'E'}

    if fog is not None:
        fog.add((r, c))
    if visit_count is not None:
        visit_count[(r, c)] = visit_count.get((r, c), 0) + 1

    if not is_endpoint:
        maze[r][c] = '@'

    if steps % skip_frames == 0:
        hud_lines = [f"Running: {title} | Steps: {steps}"]
        if active_complexity and active_complexity[0]:
            hud_lines.append(f"  {C_BIGO}📐 {active_complexity[0]}{C_END}")
        if pq_info and skip_frames < _BENCH_SKIP:
            hud_lines.append(f"  {C_PQ}🗂  PQ top: {pq_info}{C_END}")
        render(maze, "\n".join(hud_lines), fog=fog)
        if delay > 0:
            precise_sleep(delay)

    if not is_endpoint:
        actual_restore: int | str = (
            original if (original == '~' and restore_value == '.') else restore_value
        )
        if active_recording is not None:
            active_recording.append(_StepRecord(
                r, c, original, actual_restore,
                f"Running: {title} | Steps: {steps}",
            ))
        maze[r][c] = actual_restore



# --- run_mapf_animation() — Phase 3 MAPF driver ---

def run_mapf_animation(
    gen:               Generator[dict, None, None],
    maze:              list[list[int | str]],
    starts:            list[tuple[int, int]],
    goals:             list[tuple[int, int]],
    skip_frames:       int,
    delay:             float,
    algo_name:         str,
    active_complexity: list[str],
) -> MapfResult:
    """Drive a MAPF generator to completion.

    Handles: "plan" (planning phase), "step" (simulation tick),
    "conflict" (vertex collision flash), "done" (terminal).
    """
    current_positions = list(starts)
    current_paths: list[list[tuple[int, int]]] = [[] for _ in starts]

    # Track whether we were just in a CBS planning phase so we can show
    # a "now simulating" transition banner when agents start moving.
    _cbs_was_planning: bool = False

    for state in gen:
        stype = state["type"]

        # ── Planning phase ────────────────────────────────────────────────
        if stype == "plan":
            agent = state["agent"]
            steps = state["steps"]
            title = state["title"]
            if agent == -1:
                # CBS constraint-tree node. Always sync paths even on skipped
                # frames so the renderer is never stale when a frame does fire.
                if "paths" in state:
                    current_paths = state["paths"]
                _cbs_was_planning = True
                if steps % skip_frames != 0:
                    continue
                # Build a progress bar — without it CBS looks completely frozen
                # during its planning phase which can take hundreds of iterations
                _max_nodes = state.get("max_nodes", _CBS_MAX_NODES_FALLBACK)
                _pct       = min(100, int(steps / max(1, _max_nodes) * 100))
                _filled    = _pct // 5
                _bar       = f"{'█' * _filled}{'░' * (PROGRESS_BAR_WIDTH - _filled)}"
                hud = (
                    f"{C_BIGO}CBS — PLANNING PHASE{C_END}"
                    f"  [{_bar}] {_pct}%\n"
                    f"   {title}\n"
                    f"   {C_DIM}Agents are offline — CBS finds a conflict-free plan"
                    f" before anyone moves.{C_END}"
                )
            else:
                hud = (
                    f"Planning: {algo_name} | Agent {agent} → "
                    f"{state['path_len']} steps"
                )
            if active_complexity[0]:
                hud += f"\n  {C_BIGO}📐 {active_complexity[0]}{C_END}"
            render_mapf(
                maze,
                positions=current_positions,
                goals=goals,
                conflicts=state.get("conflicts", []),
                paths=current_paths,
                message=hud,
            )
            if delay > 0:
                precise_sleep(min(delay * 2, _CBS_PLAN_FRAME_MAX_SLEEP))

        # ── Simulation step ───────────────────────────────────────────────
        elif stype == "step":
            timestep  = state["timestep"]
            positions = state["positions"]
            conflicts = state["conflicts"]
            paths     = state["paths"]
            title     = state["title"]

            current_positions = positions
            current_paths     = paths

            # First tick after CBS planning — flash a transition banner so the
            # user knows the agents are now actually moving (not still planning)
            if _cbs_was_planning and timestep == 0 and skip_frames < _BENCH_SKIP:
                _cbs_was_planning = False
                _transition_hud = (
                    f"{C_PATH}CBS — SIMULATION PHASE{C_END}  "
                    f"Plan found — agents now moving\n"
                    f"   {C_DIM}Conflict-free paths computed."
                    f"  Watch agents navigate without collisions.{C_END}"
                )
                render_mapf(
                    maze,
                    positions=current_positions,
                    goals=goals,
                    conflicts=[],
                    paths=current_paths,
                    message=_transition_hud,
                )
                if delay > 0:
                    precise_sleep(_CBS_TRANSITION_HOLD)

            if timestep % skip_frames == 0:
                hud = (
                    f"Running: {title} | t={timestep}"
                    f"  |  Agents: {len(positions)}"
                    f"  |  Conflicts this tick: {len(conflicts)}"
                )
                if active_complexity[0]:
                    hud += f"\n  {C_BIGO}📐 {active_complexity[0]}{C_END}"
                render_mapf(
                    maze,
                    positions=positions,
                    goals=goals,
                    conflicts=conflicts,
                    paths=paths if skip_frames < _BENCH_SKIP else None,
                    message=hud,
                )
                if delay > 0:
                    precise_sleep(delay)

        # ── Conflict flash ────────────────────────────────────────────────
        elif stype == "conflict":
            if skip_frames < _BENCH_SKIP:
                hud = (
                    f"{C_CONFLICT}⚠  VERTEX CONFLICT at t={state['timestep']} — "
                    f"cells: {state['conflicts']}{C_END}"
                )
                render_mapf(
                    maze,
                    positions=state["positions"],
                    goals=goals,
                    conflicts=state["conflicts"],
                    paths=current_paths,
                    message=hud,
                )
                if delay > 0:
                    precise_sleep(max(delay, _MAPF_CONFLICT_FLASH_DELAY))

        # ── Done ──────────────────────────────────────────────────────────
        elif stype == "done":
            result: MapfResult = state["result"]
            message: str       = state.get("message", "")
            # Pass paths=None on the final frame — current_paths contains the
            # full simulation history which would render as a messy ghost trail
            render_mapf(
                maze,
                positions=current_positions,
                goals=goals,
                conflicts=[],
                paths=None,
                message=message,
            )
            return result

    gen.close()
    return MapfResult(0, 0.0, 0, 0, 0)



# --- run_pursuit_animation() — Phase 3 Pursuit/Pac-Man driver ---

def run_pursuit_animation(
    gen:               Generator[dict, None, None],
    maze:              list[list[int | str]],
    skip_frames:       int,
    delay:             float,
    algo_name:         str,
    active_complexity: list[str],
) -> PursuitResult:
    """Drive a pursuit generator to completion.

    Handles: "step" (movement tick), "replan" (path recalculated),
    "caught" (agent reached target), "done" (terminal).
    """
    # Track the last rendered positions for the terminal "done" render.
    # The "done" yield only carries result + message, not positions,
    # so we have to carry them forward ourselves.
    _last_agent_pos:   tuple[int, int]        = (0, 0)
    _last_target_pos:  tuple[int, int]        = (0, 0)
    _last_path:        list[tuple[int, int]]  = []
    _last_intercept:   tuple[int, int] | None = None
    _last_extra_walls: set[tuple[int, int]]   = set()

    for state in gen:
        stype = state["type"]

        if stype in ("step", "replan", "caught"):
            steps       = state["steps"]
            agent_pos   = state["agent_pos"]
            target_pos  = state["target_pos"]
            path        = state.get("path", [])
            replans     = state.get("replans", 0)
            intercept   = state.get("intercept", None)
            extra_walls = state.get("extra_walls", set())

            is_replan = (stype == "replan")
            is_caught = (stype == "caught")

            if is_caught or is_replan or (steps % skip_frames == 0):
                dist = abs(agent_pos[0] - target_pos[0]) + abs(agent_pos[1] - target_pos[1])
                hud_parts = [
                    f"Running: {state['title']} | Steps: {steps}"
                    f"  |  Replans: {replans}"
                    f"  |  Distance: {dist}",
                ]
                if is_replan and skip_frames < _BENCH_SKIP:
                    hud_parts.append(
                        f"  {C_TARGET}⟳ REPLANNING — {state['title']}{C_END}"
                    )
                if intercept is not None and skip_frames < _BENCH_SKIP:
                    hud_parts.append(
                        f"  {C_INTERCEPT}✦ Intercept target: {intercept}{C_END}"
                    )
                if is_caught:
                    hud_parts.append(f"  {C_PATH}✅ CAUGHT!{C_END}")
                if active_complexity[0]:
                    hud_parts.append(
                        f"  {C_BIGO}📐 {active_complexity[0]}{C_END}"
                    )
                if extra_walls and skip_frames < _BENCH_SKIP:
                    hud_parts.append(
                        f"  {C_HEAD}🧱 Dynamic walls: {len(extra_walls)}{C_END}"
                    )

                render_pursuit(
                    maze,
                    agent_pos=agent_pos,
                    target_pos=target_pos,
                    path=path if skip_frames < _BENCH_SKIP else [],
                    intercept=intercept if skip_frames < _BENCH_SKIP else None,
                    message="\n".join(hud_parts),
                    extra_walls=extra_walls,
                )

                pause = delay
                if is_replan and delay > 0:
                    pause = max(delay, _PURSUIT_REPLAN_FLASH_DELAY)
                if is_caught and delay > 0:
                    pause = max(delay, _PURSUIT_CAUGHT_HOLD)
                if pause > 0:
                    precise_sleep(pause)

            # Only update path/intercept/walls on "step" and "replan".
            # The "caught" yield omits those keys intentionally — overwriting
            # with .get() fallback zeros would erase the last real frame.
            _last_agent_pos  = agent_pos
            _last_target_pos = target_pos
            if stype != "caught":
                _last_path        = path
                _last_intercept   = intercept
                _last_extra_walls = extra_walls

        elif stype == "done":
            result: PursuitResult = state["result"]
            message: str          = state.get("message", "")
            render_pursuit(
                maze,
                agent_pos=_last_agent_pos,
                target_pos=_last_target_pos,
                path=[],
                intercept=None,
                message=message,
                extra_walls=_last_extra_walls,
            )
            return result

    gen.close()
    return PursuitResult(0, 0.0, False, 0)



# --- _walk_tsp_segment() — internal helper for TSP animation ---

def _walk_tsp_segment(
    maze:             list[list[int | str]],
    path:             list[tuple[int, int]],
    steps:            int,
    skip_frames:      int,
    delay:            float,
    title:            str,
    collect_target:   bool,
    active_recording: list[_StepRecord] | None,
) -> int:
    """Walk a single BFS path segment cell-by-cell and animate each step.

    Cell mutation rules:
        S / E terminals   → never mutated
        T at destination  → stamped 'c' if collect_target is True
        T in mid-path     → left as-is (pass-through)
        mud '~'           → marked '.' so finalize converts it to 'P'
        everything else   → marked '.' (visited trail)

    Returns the updated step count after walking the full segment.
    """
    if len(path) < 2:
        return steps

    dest = path[-1]

    for r, c in path[1:]:
        steps += 1
        orig   = maze[r][c]

        if orig in {'S', 'E'}:
            new_val: int | str = orig
        elif orig == 'T' and (r, c) == dest and collect_target:
            new_val = 'c'
        elif orig == 'T':
            new_val = orig  # passing through, don't collect yet
        elif orig == 'c':
            new_val = orig  # already collected — preserve the marker
        elif orig == '~':
            new_val = '.'   # mud becomes trail so finalize stamps P
        else:
            new_val = '.'

        if orig not in {'S', 'E'}:
            maze[r][c] = '@'  # transient head marker

        if steps % skip_frames == 0:
            hud = f"{title} | Steps: {steps}"
            if new_val == 'c':
                hud += f"  {C_TREASURE}✨ Treasure collected!{C_END}"
            render_tsp(maze, hud)
            if delay > 0:
                precise_sleep(delay)

        if active_recording is not None:
            hud_rec = f"{title} | Steps: {steps}"
            if new_val == 'c':
                hud_rec += f"  {C_TREASURE}✨ Treasure collected!{C_END}"
            active_recording.append(_StepRecord(r, c, orig, new_val, hud_rec))

        maze[r][c] = new_val

    return steps



# --- run_tsp_animation() — Phase 4 TSP generator driver ---

def run_tsp_animation(
    gen:              Generator[dict, None, None],
    maze:             list[list[int | str]],
    path_matrix:      list[list],
    skip_frames:      int,
    delay:            float,
    algo_name:        str,
    active_recording: list[_StepRecord] | None,
) -> TreasureRunResult:
    """Drive a TSP generator (Nearest Neighbour, Brute Force, or GA) to
    completion, rendering every animation frame.

    All three TSP algorithms share this driver — each emits the same set
    of yield types, so the dispatch logic here handles them all uniformly.
    """
    _tsp_steps: int = 0

    for state in gen:
        stype = state["type"]

        # ── Walk a path segment cell by cell ─────────────────────────────
        if stype == "segment":
            path           = state["path"]
            collect_target = state.get("collect_target", False)
            meta           = state.get("meta", {})
            algo_tag       = state.get("algo_tag", algo_name)

            # Build a coloured title string for the HUD
            if meta.get("tour_step") is not None:
                n_t   = meta.get("n_treasures", "?")
                t_idx = meta.get("treasure_idx", "?")
                title = (
                    f"{C_BIGO}{algo_tag}{C_END}"
                    f"  step {meta['tour_step']}/{n_t}"
                    f"  → T{t_idx}"
                )
            else:
                title = f"{C_BIGO}{algo_tag}{C_END}"

            _tsp_steps = _walk_tsp_segment(
                maze, path, _tsp_steps,
                skip_frames, delay, title,
                collect_target, active_recording,
            )

        # ── Convert trail marks to permanent path ─────────────────────────
        elif stype == "finalize":
            for row in maze:
                for ci, cell in enumerate(row):
                    if cell == '.':
                        row[ci] = 'P'

        # ── Brute Force progress bar ───────────────────────────────────────
        elif stype == "bf_progress":
            if skip_frames < _BENCH_SKIP:
                checked   = state["checked"]
                total     = state["total"]
                best_cost = state["best_cost"]
                pct       = min(100, int(checked / max(total, 1) * 100))
                filled    = pct // 5
                bar         = f"{'█' * filled}{'░' * (PROGRESS_BAR_WIDTH - filled)}"
                best_cost_s = "—" if best_cost == float('inf') else f"{int(best_cost)} cells"
                render_tsp(
                    maze,
                    f"🔍 Brute Force — evaluating {total:,} permutations…\n"
                    f"   [{bar}] {pct:>3}%  ({checked:,}/{total:,} checked)\n"
                    f"   {C_PATH}Best tour so far : {best_cost_s}{C_END}",
                )

        # ── Brute Force disabled (N > 8) ──────────────────────────────────
        elif stype == "bf_disabled":
            if skip_frames < _BENCH_SKIP:
                n_t    = state["n_treasures"]
                n_fact = state["n_fact"]
                render_tsp(
                    maze,
                    f"⚠️  Brute Force: {n_t} treasures → {n_t}! = {n_fact:,} "
                    f"permutations.\n"
                    f"   This would take too long.  Use Genetic Algorithm (option 3) "
                    f"instead.\n"
                    f"   Reduce treasures to N ≤ 8 to enable Brute Force.",
                )
                time.sleep(_TSP_BF_DISABLED_HOLD)

        # ── Brute Force found optimal tour — pause before animating ───────
        elif stype == "bf_announce":
            if skip_frames < _BENCH_SKIP:
                best_tour  = state["best_tour"]
                best_cost  = state["best_cost"]
                compute    = state["compute"]
                order_str  = " → ".join(f"T{t}" for t in best_tour)
                best_cost_s = "∞ (unreachable)" if best_cost == float('inf') else f"{int(best_cost)} cells"
                render_tsp(
                    maze,
                    f"✅ {C_PATH}Optimal tour found!{C_END}  "
                    f"Cost: {best_cost_s}  "
                    f"| Compute: {compute * 1000:.1f} ms\n"
                    f"   Route: S → {order_str}\n"
                    f"   Now animating the optimal route…",
                )
                time.sleep(_TSP_ANNOUNCE_HOLD)

        # ── GA live ghost-path overlay ─────────────────────────────────────
        elif stype == "ga_overlay":
            if skip_frames < _BENCH_SKIP:
                render_tsp_ga_overlay(
                    maze        = maze,
                    path_matrix = path_matrix,
                    chromosome  = state["chromosome"],
                    gen         = state["gen"],
                    total_gen   = state["total_gen"],
                    best_cost   = state["best_cost"],
                    prev_best   = state["prev_best"],
                    pop_size    = state["pop_size"],
                    stagnation  = state.get("stagnation", 0),
                    stag_limit  = state.get("stag_limit", 0),
                )
                if delay > 0:
                    precise_sleep(delay)

        # ── GA 2-opt polish phase ─────────────────────────────────────────
        elif stype == "ga_polishing":
            if skip_frames < _BENCH_SKIP:
                pre_cost = state["pre_polish_cost"]
                pre_cost_s = "∞" if pre_cost == float('inf') else str(int(pre_cost))
                render_tsp(
                    maze,
                    f"{C_GA_LIVE}🔬 2-opt polishing…{C_END}  "
                    f"Pre-polish weighted cost: {pre_cost_s}"
                    f"  {C_STAT}(GA optimises cost, not hop count){C_END}",
                )
                time.sleep(_TSP_POLISH_HOLD)

        # ── GA converged — pause before animating ─────────────────────────
        elif stype == "ga_announce":
            if skip_frames < _BENCH_SKIP:
                final_gen   = state["final_gen"]
                total_gen   = state["total_gen"]
                best_cost   = state["best_cost"]
                compute     = state["compute"]
                best_tour   = state["best_tour"]
                improvement = state["improvement"]
                order_str   = " → ".join(f"T{t}" for t in best_tour)
                polish_note = (
                    f"  {C_PATH}(2-opt saved {int(improvement)} cells){C_END}"
                    if improvement > 0.5 else ""
                )
                best_cost_s = "∞" if best_cost == float('inf') else str(int(best_cost))
                stagnated   = (final_gen < total_gen)
                conv_label  = "stagnated (no improvement)" if stagnated else "completed all generations"
                render_tsp(
                    maze,
                    f"{C_GA_LIVE}🧬 GA {conv_label} at gen "
                    f"{final_gen}/{total_gen}{C_END}"
                    f"{polish_note}\n"
                    f"   Best weighted cost: {best_cost_s}"
                    f"  {C_STAT}← GA optimises this (mud=3, road=1){C_END}\n"
                    f"   Compute: {compute * 1000:.1f} ms"
                    f"  |  Route: S → {order_str}\n"
                    f"   Hop count (steps walked) shown after animation…",
                )
                time.sleep(_TSP_ANNOUNCE_HOLD)

        # ── Unreachable treasure ───────────────────────────────────────────
        elif stype == "unreachable":
            tidx        = state["treasure_idx"]
            n_collected = state.get("n_collected", 0)
            render_tsp(
                maze,
                f"❌ {algo_name}: no path to T{tidx} — unreachable section.\n"
                f"   Collected: {n_collected} treasure(s) before failure.",
            )

        # ── Done — render final frame and return ───────────────────────────
        elif stype == "done":
            result: TreasureRunResult = state["result"]
            failed = result.total_steps == float('inf')

            if not failed:
                N = result.n_treasures
                render_tsp(
                    maze,
                    f"✅ ALL {N} TREASURES COLLECTED!\n"
                    f"   Hops (steps walked) : {int(result.total_steps)}"
                    f"  {C_STAT}← display metric{C_END}\n"
                    f"   Weighted tour cost  : {result.tour_cost}"
                    f"  {C_STAT}← what GA and Brute Force minimise (mud=3, road=1){C_END}\n"
                    f"   {C_STAT}⚡ Hops to 1st treasure: "
                    f"{result.time_to_first}{C_END}",
                )
            # Failure case: "unreachable" yield already rendered the error frame

            return result

    # Fallback — well-formed generators should never reach here
    gen.close()
    return TreasureRunResult(float('inf'), 0.0, 0, 0, (), 0, 0)
