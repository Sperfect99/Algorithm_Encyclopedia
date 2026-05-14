"""
multi_agent_solver.py — Multi-Agent Pathfinding (MAPF) module.

Three algorithms for routing multiple agents without collisions:
    1. Independent A*       — each agent plans independently (collisions possible)
    2. Prioritised Planning — agents plan in priority order, earlier agents reserve space
    3. Conflict-Based Search (CBS) — optimal algorithm that resolves conflicts iteratively

The educational comparison is: Independent A* is fast but unsafe, CBS is optimal
but exponential in the worst case, Prioritised is the practical middle ground.
"""

from __future__ import annotations

import os
import time
from typing import Generator

# ── Maze generation (shared with maze_solverV7) ───────────────────────────
from maze_genV4 import generate_maze, add_terrain, MAZE_SIZES   # type: ignore[import]

# ── Core / UI layer ────────────────────────────────────────────────────────
from core.types        import MapfResult
from ui.theme          import (
    C_BIGO, C_END, C_HEAD, C_PATH, C_START, C_WALL, C_DOT,
    C_CONFLICT, AGENT_COLORS, GOAL_COLORS,C_DIM,C_STAT,
    ansi_enable_windows,
)
from ui.terminal_utils import clear_screen, _center_ansi, _check_terminal_size, _term_width, flush_stdin
from ui.renderer       import render_mapf
from ui.animation      import run_mapf_animation

# ── MAPF algorithms ────────────────────────────────────────────────────────
from algorithms.mapf import solve_independent, solve_prioritized, solve_cbs

ansi_enable_windows()


# ===========================================================================
# ── CONSTANTS ─────────────────────────────────────────────────────────────────
# ===========================================================================

_SPEED_PRESETS: dict[str, tuple[float, int]] = {
    "1": (0.20,       1),   # Slow    — every frame, 200 ms
    "2": (0.06,       1),   # Normal  — every frame, 60 ms
    "3": (0.0,        3),   # Fast    — every 3rd frame
    "4": (0.0,  999_999),   # Instant — no animation
}

_ALGO_NAMES: dict[str, str] = {
    "1": "Independent A*",
    "2": "Prioritized Planning",
    "3": "Conflict-Based Search (CBS)",
}

_ALGO_BIG_O: dict[str, str] = {
    "Independent A*":
        "T:O(n·(V+E)logV)  S:O(n·V)  ▸ n independent heaps  (conflicts ignored)",
    "Prioritized Planning":
        "T:O(n·T·V·log(TV)) S:O(n·TV) ▸ space-time A*  (sequential reservation)",
    "Conflict-Based Search (CBS)":
        "T:O(b^d·T·V·log(TV)) S:O(b^d·TV) ▸ constraint tree  (optimal SoC)",
}

_ALGO_VERDICTS: dict[str, str] = {
    "Independent A*": (
        "Each agent plans an optimal single-agent path, ignoring all others.\n"
        "   Collisions are detected and counted but never resolved.  The\n"
        "   conflict count shows precisely WHY naive independence fails."
    ),
    "Prioritized Planning": (
        "Agents are planned in priority order.  Each agent treats the\n"
        "   prior agents' reserved (r,c,t) cells as hard constraints for\n"
        "   space-time A*.  Complete, conflict-free, but NOT optimal:\n"
        "   the first agent always takes the shortest route at others' expense."
    ),
    "Conflict-Based Search (CBS)": (
        "Two-level search: a constraint tree (CT) at the high level;\n"
        "   space-time A* at the low level.  The CT branches on every\n"
        "   detected vertex conflict, producing two children — one forbidding\n"
        "   agent i, one forbidding agent j.  Optimal (minimises SoC) but\n"
        "   exponential worst-case.  Observe how few CT nodes are needed\n"
        "   on sparse mazes — this is CBS's practical superpower."
    ),
}

_ACTIVE_COMPLEXITY: list[str] = [""]


# ===========================================================================
# ── AGENT PLACEMENT ───────────────────────────────────────────────────────────
# ===========================================================================

def _find_passable_cells(
    maze: list[list[int | str]],
) -> list[tuple[int, int]]:
    """Return all non-wall cells in the maze."""
    return [
        (r, c)
        for r, row in enumerate(maze)
        for c, cell in enumerate(row)
        if cell != 1
    ]


def _place_agents(
    maze:     list[list[int | str]],
    n_agents: int = 3,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """
    Assign start and goal positions for 'n_agents' agents.

    Strategy: divide the maze into 2*n_agents quadrant-strips and pick
    a representative cell from each.  Starts are chosen from one half of
    each strip; goals from the opposite half, ensuring spread.

    Returns: '(starts, goals)'
    """
    rows, cols = len(maze), len(maze[0])
    passable   = _find_passable_cells(maze)

    if len(passable) < n_agents * 2:
        # Very small maze — fall back to first/last N cells
        starts = [passable[i]       for i in range(n_agents)]
        goals  = [passable[-(i+1)]  for i in range(n_agents)]
        return starts, goals

    # Sort by (row + col) so we can pick from different "diagonal bands"
    passable.sort(key=lambda rc: rc[0] * cols + rc[1])
    stride = max(1, len(passable) // (n_agents * 2))

    starts: list[tuple[int, int]] = []
    goals:  list[tuple[int, int]] = []

    for i in range(n_agents):
        s_idx = (i * stride) % len(passable)
        g_idx = (len(passable) - 1 - i * stride) % len(passable)
        # Ensure distinct positions
        while (passable[s_idx] in starts or passable[s_idx] in goals):
            s_idx = (s_idx + 1) % len(passable)
        starts.append(passable[s_idx])
        while (passable[g_idx] in starts or passable[g_idx] in goals):
            g_idx = (g_idx - 1) % len(passable)
        goals.append(passable[g_idx])

    return starts, goals


# ===========================================================================
# ── DISPATCH ──────────────────────────────────────────────────────────────────
# ===========================================================================

def _dispatch(
    choice:      str,
    maze:        list[list[int | str]],
    starts:      list[tuple[int, int]],
    goals:       list[tuple[int, int]],
    delay:       float,
    skip_frames: int,
) -> MapfResult:
    """Dispatch menu choice → MAPF generator → animation driver."""
    name    = _ALGO_NAMES[choice]
    _ACTIVE_COMPLEXITY[0] = _ALGO_BIG_O.get(name, "")

    gen: Generator[dict, None, None]
    if choice == "1":
        gen = solve_independent(maze, starts, goals)
    elif choice == "2":
        gen = solve_prioritized(maze, starts, goals)
    else:
        gen = solve_cbs(maze, starts, goals)

    try:
        result = run_mapf_animation(
            gen, maze, starts, goals, skip_frames, delay, name, _ACTIVE_COMPLEXITY
        )
    finally:
        _ACTIVE_COMPLEXITY[0] = ""
    return result


# ===========================================================================
# ── REPORT CARD ───────────────────────────────────────────────────────────────
# ===========================================================================

def _show_report_card(
    algo_name: str,
    result:    MapfResult,
    n_agents:  int,
) -> None:
    """Display a structured post-run statistics panel."""
    W       = 72
    verdict = _ALGO_VERDICTS.get(algo_name, "")

    print("\n" + "═" * W)
    print(_center_ansi(f"📊  MAPF REPORT CARD — {algo_name}", W))
    print("═" * W)
    print(f"  {'Agents':<32}: {n_agents}")
    print(f"  {'Makespan (timesteps)':<32}: {result.makespan}")
    print(f"  {'Sum-of-Costs (SoC)':<32}: {result.sum_of_costs}")
    conflict_note = "  (conflict cells per tick, summed)" if result.collisions > 0 else "  ✅ conflict-free"
    print(f"  {'Vertex Conflicts':<32}: {result.collisions}{conflict_note}")
    if algo_name == "Independent A*" and result.collisions == 0:
        print(
            f"  {C_DIM}  └ 0 conflicts here — but this is layout-dependent,\n"
            f"     not a guarantee. Regenerate or add agents to see failures.{C_END}"
        )
    print(f"  {'Compute Time':<32}: {result.compute_time * 1000:.2f} ms")
    bigo = _ALGO_BIG_O.get(algo_name, "")
    if bigo:
        print(f"  {C_BIGO}{'Complexity':<32}: {bigo}{C_END}")
    if verdict:
        print("─" * W)
        print(f"  💡 {verdict}")
    print("═" * W)


# ===========================================================================
# ── COMPARISON MODE ───────────────────────────────────────────────────────────
# ===========================================================================

def _run_comparison(
    maze:        list[list[int | str]],
    starts:      list[tuple[int, int]],
    goals:       list[tuple[int, int]],
    n_agents:    int,
) -> None:
    """
    Run all three MAPF algorithms on the same maze (instant mode) and print
    a side-by-side leaderboard.
    """
    clear_screen()
    print("\n" + "═" * 72)
    print("⚔️   MAPF ALGORITHM COMPARISON  ⚔️".center(72))
    print("═" * 72)
    print(f"  Maze: {len(maze)}×{len(maze[0])}  |  Agents: {n_agents}")
    print("  Running all three algorithms instantly…\n")

    results: dict[str, MapfResult] = {}
    for choice, name in _ALGO_NAMES.items():
        maze_copy = [row[:] for row in maze]
        r = _dispatch(choice, maze_copy, starts, goals, 0.0, 999_999)
        results[name] = r
        print(f"  ✔ {name} done.")

    W = 72
    print("\n" + "═" * W)
    print("🏆  COMPARISON RESULTS  🏆".center(W))
    print("═" * W)
    print(
        f"  {'Algorithm':<32} {'Makespan':>10} {'SoC':>8} "
        f"{'Conflicts':>10} {'Time (ms)':>10}"
    )
    print("─" * W)
    for name, r in results.items():
        print(
            f"  {name:<32} {r.makespan:>10} {r.sum_of_costs:>8} "
            f"{r.collisions:>10} {r.compute_time * 1000:>10.2f}"
        )
    print("═" * W)

    # Highlight winner (lowest SoC for conflict-free runs)
    conflict_free = {n: r for n, r in results.items() if r.collisions == 0}
    if conflict_free:
        best_name = min(conflict_free, key=lambda n: conflict_free[n].sum_of_costs)
        best      = conflict_free[best_name]
        soc_vals  = [r.sum_of_costs for r in conflict_free.values()]
        all_tied  = len(set(soc_vals)) == 1
        print(
            f"\n  {C_PATH}🏅 Best SoC (conflict-free): {best_name} "
            f"(SoC={best.sum_of_costs}){C_END}"
        )
        if all_tied and n_agents <= 3:
            print(
                f"  {C_DIM}💡 All conflict-free algorithms found identical SoC on this small instance.\n"
                f"     CBS's optimality advantage emerges on denser mazes with ≥4 agents.{C_END}"
            )

    print()
    input(f"👉 Press {C_PATH}ENTER{C_END} to continue…")


# ===========================================================================
# ── SETUP ─────────────────────────────────────────────────────────────────────
# ===========================================================================

def _prompt_speed() -> tuple[float, int]:
    print("\nSelect animation speed:")
    print("  1. Slow    — every frame, 200 ms  (planning phase visible)")
    print("  2. Normal  — every frame, 60 ms   (default)")
    print("  3. Fast    — every 3rd frame")
    print("  4. Instant — no animation          (for comparison only)")
    while True:
        c = input("Speed (1-4): ").strip()
        if c in _SPEED_PRESETS:
            return _SPEED_PRESETS[c]
        print("  Enter 1–4.")


def setup_new_session() -> tuple[
    list[list[int | str]], float, int, bool,
    list[tuple[int, int]], list[tuple[int, int]], int,
]:
    """
    Interactive setup: maze size, speed, terrain, agent count, placement.

    Returns:
        (maze, delay, skip_frames, terrain_active, starts, goals, n_agents)
    """
    clear_screen()
    _SIZE_LABELS = {
        0: "tiny", 1: "tiny", 2: "small", 3: "small", 4: "medium",
        5: "medium", 6: "large", 7: "large", 8: "huge", 9: "huge", 10: "massive",
    }
    print("\n" + "═" * 60)
    print("🤖  MULTI-AGENT PATHFINDING SOLVER  V3  🤖".center(60))
    print("═" * 60)
    print("\nSelect Maze Complexity Level:\n")
    for lvl, (r, c) in MAZE_SIZES.items():
        label = _SIZE_LABELS.get(lvl, "")
        print(f"  {lvl:>2}  →  {r:>2} × {c:<3} grid  ({label})")

    print()
    while True:
        try:
            comp = int(input("Enter level (0-10): "))
            if 0 <= comp <= 10:
                break
            print("  Please enter 0–10.")
        except ValueError:
            print("  Invalid input.")

    maze_rows, maze_cols = MAZE_SIZES[comp]
    _check_terminal_size(maze_rows, maze_cols)

    delay, skip_frames = _prompt_speed()

    terrain_active = False
    if comp >= 3:
        while True:
            ans = input("\nAdd mud terrain (weighted, cost 3)? (y/n): ").strip().lower()
            if ans in {'y', 'yes', 'n', 'no'}:
                break
        if ans in {'y', 'yes'}:
            terrain_active = True

    print(
        f"\n  {C_DIM}2–3 agents: algorithms usually agree (good for learning basics)\n"
        f"  4–5 agents: conflicts multiply — CBS vs PP tradeoffs become visible{C_END}"
    )
    while True:
        try:
            n = int(input("Number of agents (2–5): "))
            if 2 <= n <= 5:
                break
            print("  Enter a number from 2 to 5.")
        except ValueError:
            print("  Invalid input.")
    n_agents = n

    print("\n⏳ Generating maze… Please wait!")
    maze = generate_maze(comp)
    if terrain_active:
        add_terrain(maze)

    starts, goals = _place_agents(maze, n_agents)

    print(f"\n  Placed {n_agents} agents:")
    for i, (s, g) in enumerate(zip(starts, goals)):
        col   = AGENT_COLORS[i % len(AGENT_COLORS)]
        gcol  = GOAL_COLORS[i % len(GOAL_COLORS)]
        print(
            f"    Agent {i}: start={col}{s}{C_END}  →  goal={gcol}{g}{C_END}"
        )

    return maze, delay, skip_frames, terrain_active, starts, goals, n_agents


# ===========================================================================
# ── ENTRY POINT ───────────────────────────────────────────────────────────────
# ===========================================================================

def main() -> None:
    """Entry point with clean KeyboardInterrupt / EOFError handling."""
    try:
        _main_loop()
    except (KeyboardInterrupt, EOFError):
        print("\033[0m\n\nInterrupted — goodbye! 🤖\n")


def _main_loop() -> None:
    """Interactive session loop."""
    maze, delay, skip_frames, terrain_active, starts, goals, n_agents = setup_new_session()

    while True:
        rows, cols = len(maze), len(maze[0])

        _SPEED_NAMES = {"1": "Slow", "2": "Normal", "3": "Fast", "4": "Instant"}
        speed_lbl = next(
            (n for k, n in _SPEED_NAMES.items()
             if _SPEED_PRESETS[k] == (delay, skip_frames)),
            "Custom",
        )
        terrain_lbl = (
            f"\033[38;5;130mON{C_END}" if terrain_active
            else f"{C_DOT}OFF{C_END}"
        )

        W = _term_width()
        print("\n" + "═" * W)
        print(_center_ansi("🤖  MULTI-AGENT PATHFINDING  V3  🤖", W))
        print("═" * W)
        print(
            f"  Maze: {C_BIGO}{rows}×{cols}{C_END}"
            f"  |  Speed: {C_DOT}{speed_lbl}{C_END}"
            f"  |  Terrain: {terrain_lbl}"
            f"  |  Agents: {C_HEAD}{n_agents}{C_END}"
        )
        print()

        for i, (s, g) in enumerate(zip(starts, goals)):
            color = AGENT_COLORS[i % len(AGENT_COLORS)]
            gcol  = GOAL_COLORS[i % len(GOAL_COLORS)]
            print(
                f"    {color}A{i}{C_END} start={color}{s}{C_END}"
                f"  →  {gcol}G{i}{C_END}={gcol}{g}{C_END}"
            )

        print()
        print("  ─── MAPF Algorithms ─────────────────────────────────")
        print("  1.  Independent A*          (baseline; shows collisions)")
        print("  2.  Prioritized Planning    (conflict-free; suboptimal)")
        print("  3.  Conflict-Based Search   (optimal SoC; CBS — shows its power at ≥4 agents)")
        print()
        print("  ─── Session ─────────────────────────────────────────")
        print("  4.  ⚔️  Algorithm Comparison  (run all 3, compare metrics)")
        print("  5.  📚  Tutorial")
        print("  0.  Exit")
        print("─" * W)

        choice = input("Choose (0–5): ").strip()

        # ── Algorithm run ─────────────────────────────────────────────────
        if choice in ("1", "2", "3"):
            name      = _ALGO_NAMES[choice]
            maze_copy = [row[:] for row in maze]
            result    = _dispatch(choice, maze_copy, starts, goals, delay, skip_frames)

            from ui.terminal_utils import flush_stdin
            flush_stdin()
            flush_stdin()
            input(f"\n👉 Press {C_PATH}ENTER{C_END} to see Report Card…")
            _show_report_card(name, result, n_agents)

        elif choice == "4":
            maze_copy = [row[:] for row in maze]
            _run_comparison(maze_copy, starts, goals, n_agents)
            continue

        elif choice == "5":
            _show_tutorial()
            continue

        elif choice == "0":
            print("\nGoodbye! 🤖\n")
            break

        else:
            print("  Invalid option — try again.")
            continue

        # ── New-maze prompt ───────────────────────────────────────────────
        # ENTER or 'n' keeps the current maze; 'y' generates a fresh one.
        while True:
            ans = input("\n  [ENTER/n] keep this maze   [y] generate new maze: ").strip().lower()
            if ans in {'y', 'yes'}:
                (maze, delay, skip_frames, terrain_active,
                 starts, goals, n_agents) = setup_new_session()
                maze_copy = []
                break
            elif ans in {'n', 'no', ''}:
                break
            else:
                print("  Please answer y or n.")


# ===========================================================================
# ── TUTORIAL ──────────────────────────────────────────────────────────────────
# ===========================================================================

def _show_tutorial() -> None:
    clear_screen()
    _TW = _term_width()
    print("\n" + "═" * _TW)
    print(_center_ansi("📚  MAPF TUTORIAL — MULTI-AGENT PATHFINDING  📚", _TW))
    print("═" * _TW)
    print(
        "\n  MAPF asks: given n agents each with a start and goal, find\n"
        "  collision-free paths for all agents.  Two conflict types:\n"
        "    Vertex conflict: agents i and j at same cell at same time t.\n"
        "    Edge   conflict: agents swap positions between t and t+1.\n"
        "  (This visualiser handles vertex conflicts; CBS is easy to extend.)\n"
        "\n  Space-Time A* (used by Prioritized Planning and CBS):\n"
        "  Extends plain A* (Domain 1) by adding a time dimension.\n"
        "    State : (row, col, timestep) instead of just (row, col).\n"
        "    Actions: move to neighbour  OR  wait in place (both cost 1).\n"
        "    Constraints: forbidden (r,c,t) cells block that state only.\n"
        "  This lets agents plan detours through TIME, not just space.\n"
        "\n  Two competing optimality objectives:\n"
        f"    {C_BIGO}Makespan{C_END}        — time until the LAST agent reaches its goal.\n"
        "                   Minimise this if all agents must finish together.\n"
        f"    {C_BIGO}Sum-of-Costs (SoC){C_END} — total moves across ALL agents.\n"
        "                   Minimise this to reduce collective effort.\n"
        "  These conflict: making one agent wait (increases SoC) can reduce\n"
        "  Makespan.  CBS minimises SoC; Prioritized Planning does not\n"
        "  guarantee either.  Watch both columns in the comparison table.\n"
    )
    entries = [
        (
            "1. Independent A*  (baseline)",
            "  Plans n independent A* paths.  Fastest to compute.\n"
            "   Conflicts are detected and counted but never resolved.\n"
            "   Shows empirically why naive independence fails.\n"
            f"   {C_BIGO}T:O(n·(V+E)logV)  S:O(n·V){C_END}",
        ),
        (
            "2. Prioritized Planning  (Silver 2005)",
            "  Plans agents sequentially.  Agent 0 plans freely.\n"
            "   Each later agent treats prior agents' (r,c,t) as forbidden\n"
            "   and uses space-time A* to route around them.\n"
            "   Complete; NOT optimal — priority ordering matters enormously.\n"
            f"   {C_BIGO}T:O(n·T·V·log(T·V))  S:O(n·T·V){C_END}",
        ),
        (
            "3. Conflict-Based Search — CBS  (Sharon et al. 2012)",
            "  Two-level search over a constraint tree (CT).\n"
            "   High level: best-first expansion of CT nodes by SoC.\n"
            "   Low level:  space-time A* per agent under constraints.\n"
            "   On conflict: branch CT — forbid agent i OR agent j.\n"
            "   Optimal (minimises sum-of-costs); exponential worst-case.\n"
            "   On sparse maps CBS expands very few nodes — watch the counter.\n"
            f"   {C_BIGO}T:O(b^d·T·V·log(T·V))  S:O(b^d·T·V){C_END}",
        ),
    ]
    for title, desc in entries:
        print(f"\n  {C_START}{title}:{C_END}")
        print(f"   {desc}")

    print("\n" + "═" * _TW)
    print(
        f"\n  Legend:  "
        f"{AGENT_COLORS[0]}0{C_END}=Agent0  "
        f"{AGENT_COLORS[1]}1{C_END}=Agent1  "
        f"{AGENT_COLORS[2]}2{C_END}=Agent2  "
        f"{GOAL_COLORS[0]}a{C_END}=Goal0  "
        f"{GOAL_COLORS[1]}b{C_END}=Goal1  "
        f"{GOAL_COLORS[2]}c{C_END}=Goal2  "
        f"{C_CONFLICT}!{C_END}=Conflict"
    )
    input(f"\n👉 Press {C_PATH}ENTER{C_END} to return…")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Downstream pipe consumer closed early (e.g. `python ... | head`).
        # Flush stderr and exit silently — no traceback, exit code 0.
        import sys
        sys.stderr.close()
        sys.exit(0)
