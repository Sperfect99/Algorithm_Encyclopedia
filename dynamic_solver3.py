"""
dynamic_solver3.py — Pursuit-Evasion (Pac-Man Mode) module.

Three pursuit strategies on a live maze where the target moves:
    1. Naive Recalculation  — full A* replan every single tick
    2. Dynamic Repair       — only replans when the path is blocked or target drifts too far
    3. Greedy Intercept     — predicts where the target is going and cuts it off

The key metric is replan frequency: Naive always replans (replans == steps),
Dynamic Repair replans rarely (replans << steps). The Greedy variant adds
path prediction on top of the repair strategy.
"""

from __future__ import annotations

import random
import time
from typing import Generator

from maze_genV4 import generate_maze, add_terrain, MAZE_SIZES   # type: ignore[import]

from core.types        import PursuitResult
from ui.theme          import (
    C_BIGO, C_END, C_HEAD, C_PATH, C_TARGET, C_INTERCEPT, C_DOT,
    C_CONFLICT, C_WALL,
    ansi_enable_windows,
)
from ui.terminal_utils import clear_screen, _center_ansi, _check_terminal_size, _term_width, flush_stdin
from ui.renderer       import render_pursuit
from ui.animation      import run_pursuit_animation

from algorithms.pursuit import (
    solve_naive, solve_dynamic_repair, solve_greedy_intercept,
)

ansi_enable_windows()


# ===========================================================================
# ── CONSTANTS ─────────────────────────────────────────────────────────────────
# ===========================================================================

_SPEED_PRESETS: dict[str, tuple[float, int]] = {
    "1": (0.20,       1),
    "2": (0.08,       1),
    "3": (0.0,        3),
    "4": (0.0,  999_999),
}

_ALGO_NAMES: dict[str, str] = {
    "1": "Naive Recalculation",
    "2": "Dynamic Repair",
    "3": "Greedy Intercept",
}

_ALGO_BIG_O: dict[str, str] = {
    "Naive Recalculation":
        "T:O(steps·(V+E)logV)  S:O(V)  ▸ full A* every tick  (replans = steps)",
    "Dynamic Repair":
        "T:O(repairs·(V+E)logV)  S:O(V) ▸ cache + repair  (repairs << steps)",
    "Greedy Intercept":
        "T:O(replans·(V+E)logV)  S:O(V) ▸ velocity projection + A* to intercept",
}

_ALGO_VERDICTS: dict[str, str] = {
    "Naive Recalculation": (
        "Recomputes A* from scratch on every single tick — the maximum\n"
        "   possible replanning overhead.  On a static maze it gives optimal\n"
        "   results.  Use the replans/steps = 1.0 ratio as your baseline."
    ),
    "Dynamic Repair": (
        "Caches the current path.  Replanning is triggered only by:\n"
        "   (a) Target drift > threshold — path goal is stale.\n"
        "   (b) New wall blocks a cached cell — path is invalid.\n"
        "   The replans/steps ratio shows how much computation was saved.\n"
        "   D* Lite extends this idea to propagate costs incrementally."
    ),
    "Greedy Intercept": (
        "Projects the target's current velocity vector N steps forward\n"
        "   and runs A* toward that predicted intercept point.  On a target\n"
        "   moving in a corridor the pursuer can 'wait at the exit' rather\n"
        "   than chasing from behind — dramatically reducing steps on\n"
        "   directional evaders.  Degrades to Naive on random walkers."
    ),
}

_ACTIVE_COMPLEXITY: list[str] = [""]

_PASSABLE: frozenset[int | str] = frozenset({0, '~', 'S', 'E'})


# ===========================================================================
# ── POSITION UTILITIES ────────────────────────────────────────────────────────
# ===========================================================================

def _find_passable_cells(
    maze: list[list[int | str]],
) -> list[tuple[int, int]]:
    return [
        (r, c)
        for r, row in enumerate(maze)
        for c, cell in enumerate(row)
        if cell in _PASSABLE
    ]


def _place_agent_target(
    maze: list[list[int | str]],
) -> tuple[tuple[int, int], tuple[int, int]]:
    """
    Randomly place agent and target on passable cells with a guaranteed
    minimum Manhattan distance of at least (cols // 2).
    """
    passable = _find_passable_cells(maze)
    cols     = len(maze[0])
    min_dist = max(cols // 2, 3)

    if len(passable) < 2:
        return passable[0], passable[0]

    shuffled = list(passable)
    random.shuffle(shuffled)

    agent = shuffled[0]
    for candidate in shuffled[1:]:
        if abs(candidate[0] - agent[0]) + abs(candidate[1] - agent[1]) >= min_dist:
            return agent, candidate

    # Fallback: no pair meets min_dist — pick the farthest available cell
    target = max(shuffled[1:], key=lambda p: abs(p[0] - agent[0]) + abs(p[1] - agent[1]))
    return agent, target


def _random_passable(
    maze: list[list[int | str]],
    exclude: set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """Pick a random passable cell, optionally excluding certain cells."""
    passable = _find_passable_cells(maze)
    exclude  = exclude or set()
    options  = [p for p in passable if p not in exclude]
    return random.choice(options) if options else passable[0]


# ===========================================================================
# ── DYNAMIC WALL SCHEDULE BUILDER ────────────────────────────────────────────
# ===========================================================================

def _build_wall_schedule(
    maze:          list[list[int | str]],
    agent_start:   tuple[int, int],
    target_start:  tuple[int, int],
    n_walls:       int,
    max_step:      int = 300,
) -> list[tuple[int, tuple[int, int]]]:
    """
    Randomly schedule 'n_walls' new wall appearances during the run.

    Walls are placed on passable cells that are neither the agent start
    nor the target start.  Each wall appears at a distinct timestep.
    """
    passable = _find_passable_cells(maze)
    excluded = {agent_start, target_start}
    candidates = [p for p in passable if p not in excluded]
    random.shuffle(candidates)
    cells   = candidates[:n_walls]
    steps   = sorted(random.sample(range(10, max_step), min(n_walls, max_step - 10)))
    return list(zip(steps, cells))


# ===========================================================================
# ── DISPATCH ──────────────────────────────────────────────────────────────────
# ===========================================================================

def _dispatch(
    choice:               str,
    maze:                 list[list[int | str]],
    agent_start:          tuple[int, int],
    target_start:         tuple[int, int],
    delay:                float,
    skip_frames:          int,
    evasive:              bool,
    wall_schedule:        list[tuple[int, tuple[int, int]]],
    lookahead:            int = 5,
    repair_threshold:     int = 3,
) -> PursuitResult:
    """Dispatch menu choice → pursuit generator → animation driver."""
    name = _ALGO_NAMES[choice]
    _ACTIVE_COMPLEXITY[0] = _ALGO_BIG_O.get(name, "")

    gen: Generator[dict, None, None]
    if choice == "1":
        gen = solve_naive(maze, agent_start, target_start, evasive, wall_schedule)
    elif choice == "2":
        gen = solve_dynamic_repair(
            maze, agent_start, target_start, evasive,
            wall_schedule, repair_threshold,
        )
    else:
        gen = solve_greedy_intercept(
            maze, agent_start, target_start, evasive,
            wall_schedule, lookahead,
        )

    try:
        result = run_pursuit_animation(gen, maze, skip_frames, delay, name, _ACTIVE_COMPLEXITY)
    finally:
        _ACTIVE_COMPLEXITY[0] = ""
    return result


# ===========================================================================
# ── REPORT CARD ───────────────────────────────────────────────────────────────
# ===========================================================================

def _show_report_card(
    algo_name:   str,
    result:      PursuitResult,
    evasive:     bool,
    n_walls:     int,
    lookahead:   int,
    threshold:   int,
) -> None:
    W       = 72
    verdict = _ALGO_VERDICTS.get(algo_name, "")

    print("\n" + "═" * W)
    print(_center_ansi(f"📊  PURSUIT REPORT CARD — {algo_name}", W))
    print("═" * W)
    print(f"  {'Target behaviour':<36}: {'Evasive' if evasive else 'Random walk'}")
    print(f"  {'Dynamic walls added':<36}: {n_walls}")
    if algo_name == "Greedy Intercept":
        print(f"  {'Velocity lookahead':<36}: {lookahead} steps")
    if algo_name == "Dynamic Repair":
        if threshold == 1:
            threshold_note = "  ← = Naive (replans every tick)"
        elif threshold >= 7:
            threshold_note = "  ← high: may chase stale paths on fast targets"
        else:
            threshold_note = ""
        print(f"  {'Repair threshold (drift)':<36}: {threshold} cells{threshold_note}")
    print()
    outcome = f"{C_PATH}CAUGHT ✅{C_END}" if result.caught else f"{C_CONFLICT}ESCAPED ❌{C_END}"
    print(f"  {'Outcome':<36}: {outcome}")
    print(f"  {'Steps taken':<36}: {result.steps}")
    print(f"  {'Path replans':<36}: {result.replans}")
    if result.steps > 0:
        ratio = result.replans / result.steps
        ratio_note = (
            "  ← > 1.0: initial t=0 plan pre-counted before first step"
            if ratio > 1.0 else ""
        )
        print(f"  {'Replan ratio (replans/steps)':<36}: {ratio:.3f}{ratio_note}")
        if algo_name == "Dynamic Repair":
            savings = max(0, result.steps - result.replans)
            overhead_note = (
                "  ← path-blocked check runs every tick regardless"
                if ratio > 0.7 else ""
            )
            print(f"  {'Replans avoided vs Naive':<36}: ≈{savings}{overhead_note}")
            print(
                f"  {C_DIM}  (cache bookkeeping cost paid on all {result.steps} "
                f"ticks; A* cost saved on {savings}){C_END}"
            )
        if algo_name == "Greedy Intercept" and not evasive and ratio > 0.85:
            print(
                f"\n  {C_DIM}💡 Intercept note: ratio≈1.0 on a Random target — velocity\n"
                f"     prediction has no signal to exploit.  Behaviour degrades to\n"
                f"     Naive.  Switch to Evasive target to see lookahead pay off.{C_END}"
            )
    print(f"  {'Compute time':<36}: {result.compute_time * 1000:.2f} ms")
    bigo = _ALGO_BIG_O.get(algo_name, "")
    if bigo:
        print(f"  {C_BIGO}{'Complexity':<36}: {bigo}{C_END}")
    if verdict:
        print("─" * W)
        print(f"  💡 {verdict}")
    print("═" * W)


# ===========================================================================
# ── COMPARISON MODE ───────────────────────────────────────────────────────────
# ===========================================================================

def _run_comparison(
    maze:          list[list[int | str]],
    agent_start:   tuple[int, int],
    target_start:  tuple[int, int],
    evasive:       bool,
    wall_schedule: list[tuple[int, tuple[int, int]]],
    lookahead:     int,
    threshold:     int,
) -> None:
    """Run all three algorithms on the same scenario and compare."""
    clear_screen()
    _CW = _term_width()
    print("\n" + "═" * _CW)
    print(_center_ansi("⚔️   PURSUIT ALGORITHM COMPARISON  ⚔️", _CW))
    print("═" * _CW)
    fairness_note = (
        ""
        if evasive else
        f"\n  {C_DIM}⚠ Random target: each algorithm sees different random moves\n"
        f"  (sequential runs, shared RNG). Use Evasive for a controlled comparison.{C_END}"
    )
    print(
        f"  Target: {'Evasive' if evasive else 'Random'}  |  "
        f"Dynamic walls: {len(wall_schedule)}"
        f"{fairness_note}\n"
    )
    print("  Running all three algorithms instantly…\n")

    results: dict[str, PursuitResult] = {}
    for choice, name in _ALGO_NAMES.items():
        maze_copy = [row[:] for row in maze]
        r = _dispatch(
            choice, maze_copy, agent_start, target_start,
            0.0, 999_999, evasive, wall_schedule, lookahead, threshold,
        )
        results[name] = r
        status = "CAUGHT ✅" if r.caught else "ESCAPED ❌"
        print(f"  ✔ {name}: {status}  ({r.steps} steps, {r.replans} replans)")

    W = _CW
    print("\n" + "═" * W)
    print(_center_ansi("🏆  COMPARISON RESULTS  🏆", W))
    print("═" * W)
    print(
        f"  {'Algorithm':<28} {'Outcome':>8} {'Steps':>7} "
        f"{'Replans':>8} {'Ratio':>7} {'Time ms':>9}"
    )
    print("─" * W)
    for name, r in results.items():
        outcome = "CAUGHT" if r.caught else "ESCAPED"
        ratio   = f"{r.replans/r.steps:.3f}" if r.steps else "—"
        print(
            f"  {name:<28} {outcome:>8} {r.steps:>7} "
            f"{r.replans:>8} {ratio:>7} {r.compute_time * 1000:>9.2f}"
        )
    print("═" * W)

    # Efficiency highlight
    caught = {n: r for n, r in results.items() if r.caught}
    if len(caught) > 1:
        fewest = min(caught, key=lambda n: caught[n].steps)
        most_efficient = min(caught, key=lambda n: caught[n].replans / max(caught[n].steps, 1))
        print(f"\n  {C_PATH}🏅 Fewest steps: {fewest} ({caught[fewest].steps}){C_END}")
        print(f"  {C_PATH}🏅 Most efficient: {most_efficient} "
              f"(ratio={caught[most_efficient].replans/max(caught[most_efficient].steps,1):.3f}){C_END}")

    print()
    input(f"👉 Press {C_PATH}ENTER{C_END} to continue…")


# ===========================================================================
# ── SETUP ─────────────────────────────────────────────────────────────────────
# ===========================================================================

def _prompt_speed() -> tuple[float, int]:
    print("\nSelect animation speed:")
    print("  1. Slow    — every frame, 200 ms")
    print("  2. Normal  — every frame, 80 ms   (default)")
    print("  3. Fast    — every 3rd frame")
    print("  4. Instant — no animation")
    while True:
        c = input("Speed (1-4): ").strip()
        if c in _SPEED_PRESETS:
            return _SPEED_PRESETS[c]
        print("  Enter 1–4.")


def _prompt_scenario(
    maze:         list[list[int | str]],
    agent_start:  tuple[int, int],
    target_start: tuple[int, int],
) -> tuple[bool, list[tuple[int, tuple[int, int]]], int, int]:
    """
    Prompt user for scenario parameters:
        - Target behaviour (random / evasive)
        - Dynamic wall count
        - Lookahead (Greedy Intercept)
        - Repair threshold (Dynamic Repair)

    Returns: (evasive, wall_schedule, lookahead, repair_threshold)
    """
    print("\n  Target behaviour:")
    print("  1. Random walk    — picks a uniformly random valid neighbour")
    print("  2. Evasive        — greedy one-step: maximises distance each tick")
    print("                      (may corner itself — not a true adversarial planner)")
    while True:
        t = input("  Target (1/2): ").strip()
        if t in ("1", "2"):
            break
        print("  Enter 1 or 2.")
    evasive = (t == "2")

    while True:
        try:
            nw = int(input("\n  Dynamic walls (0–10, default 0): ").strip() or "0")
            if 0 <= nw <= 10:
                break
            print("  Enter 0–10.")
        except ValueError:
            print("  Invalid input.")

    wall_schedule: list[tuple[int, tuple[int, int]]] = []
    if nw > 0:
        wall_schedule = _build_wall_schedule(maze, agent_start, target_start, nw)
        print(
            f"\n  {C_WALL}🧱 {nw} walls will appear at timesteps: "
            f"{sorted(t for t, _ in wall_schedule)}{C_END}"
        )

    while True:
        try:
            la = int(input("\n  Greedy Intercept lookahead (2–10, default 5): ").strip() or "5")
            if 2 <= la <= 10:
                break
            print("  Enter 2–10.")
        except ValueError:
            print("  Invalid input.")

    while True:
        try:
            rt = int(input("  Dynamic Repair threshold (1–8, default 3): ").strip() or "3")
            if 1 <= rt <= 8:
                break
            print("  Enter 1–8.")
        except ValueError:
            print("  Invalid input.")

    return evasive, wall_schedule, la, rt


def setup_new_session() -> tuple[
    list[list[int | str]], float, int, bool,
    tuple[int, int], tuple[int, int],
]:
    """
    Interactive setup.
    Returns: (maze, delay, skip_frames, terrain_active, agent_start, target_start)
    """
    clear_screen()
    _SIZE_LABELS = {
        0: "tiny", 1: "tiny", 2: "small", 3: "small", 4: "medium",
        5: "medium", 6: "large", 7: "large", 8: "huge", 9: "huge", 10: "massive",
    }
    print("\n" + "═" * 60)
    print("🎯  DYNAMIC PURSUIT SOLVER  V3  (Pac-Man Mode)  🎯".center(60))
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
            ans = input("\nAdd mud terrain (cost 3)? (y/n): ").strip().lower()
            if ans in {'y', 'yes', 'n', 'no'}:
                break
        if ans in {'y', 'yes'}:
            terrain_active = True

    print("\n⏳ Generating maze… Please wait!")
    maze = generate_maze(comp)
    if terrain_active:
        add_terrain(maze)

    agent_start, target_start = _place_agent_target(maze)
    print(
        f"\n  {C_PATH}►{C_END} Agent  start: {agent_start}"
        f"    {C_TARGET}◆{C_END} Target start: {target_start}"
    )

    return maze, delay, skip_frames, terrain_active, agent_start, target_start


# ===========================================================================
# ── ENTRY POINT ───────────────────────────────────────────────────────────────
# ===========================================================================

def main() -> None:
    """Entry point with clean interrupt handling."""
    try:
        _main_loop()
    except (KeyboardInterrupt, EOFError):
        print("\033[0m\n\nInterrupted — goodbye! 🎯\n")


def _main_loop() -> None:
    """Interactive session loop."""
    (maze, delay, skip_frames, terrain_active,
     agent_start, target_start) = setup_new_session()

    # Scenario parameters (persist across runs until user changes them)
    evasive:       bool                              = True
    wall_schedule: list[tuple[int, tuple[int, int]]] = []
    lookahead:     int                               = 5
    threshold:     int                               = 3

    while True:
        rows, cols = len(maze), len(maze[0])

        _SPEED_NAMES = {"1": "Slow", "2": "Normal", "3": "Fast", "4": "Instant"}
        speed_lbl = next(
            (n for k, n in _SPEED_NAMES.items()
             if _SPEED_PRESETS[k] == (delay, skip_frames)),
            "Custom",
        )
        evade_lbl    = f"{C_TARGET}Evasive{C_END}" if evasive else f"{C_DOT}Random{C_END}"
        terrain_lbl  = f"\033[38;5;130mON{C_END}" if terrain_active else f"{C_DOT}OFF{C_END}"
        walls_lbl    = (
            f"\033[38;5;208m{len(wall_schedule)} walls{C_END}"
            if wall_schedule else f"{C_DOT}none{C_END}"
        )

        W = _term_width()
        print("\n" + "═" * W)
        print(_center_ansi("🎯  DYNAMIC PURSUIT SOLVER  V3  🎯", W))
        print("═" * W)
        print(
            f"  Maze: {C_BIGO}{rows}×{cols}{C_END}"
            f"  |  Speed: {C_DOT}{speed_lbl}{C_END}"
            f"  |  Terrain: {terrain_lbl}"
        )
        print(
            f"  Target: {evade_lbl}"
            f"  |  Walls: {walls_lbl}"
            f"  |  Lookahead: {C_INTERCEPT}{lookahead}{C_END}"
            f"  |  Threshold: {C_BIGO}{threshold}{C_END}"
        )
        print(
            f"  {C_PATH}►{C_END} Agent:  {agent_start}"
            f"    {C_TARGET}◆{C_END} Target: {target_start}"
        )
        print()
        print("  ─── Pursuit Algorithms ───────────────────────────────")
        print("  1.  Naive Recalculation   (A* every tick — baseline)")
        print("  2.  Dynamic Repair        (cache + repair — efficient)")
        print(f"  3.  Greedy Intercept      (velocity projection, lookahead={lookahead})")
        print()
        print("  ─── Session ──────────────────────────────────────────")
        print("  4.  ⚔️  Algorithm Comparison  (all 3 on same scenario)")
        print("  5.  ⚙️  Configure Scenario    (target / walls / params)")
        print("  6.  📚  Tutorial")
        print("  0.  Exit")
        print("─" * W)

        choice = input("Choose (0–6): ").strip()

        # ── Algorithm run ─────────────────────────────────────────────────
        if choice in ("1", "2", "3"):
            name      = _ALGO_NAMES[choice]
            maze_copy = [row[:] for row in maze]
            # wall_schedule coordinates were built for the current agent_start/target_start.
            # They remain valid as long as neither is regenerated (new maze resets both).
            result    = _dispatch(
                choice, maze_copy, agent_start, target_start,
                delay, skip_frames, evasive, wall_schedule, lookahead, threshold,
            )

            flush_stdin()
            input(f"\n👉 Press {C_PATH}ENTER{C_END} to see Report Card…")
            _show_report_card(
                name, result, evasive, len(wall_schedule), lookahead, threshold
            )

        elif choice == "4":
            maze_copy = [row[:] for row in maze]
            _run_comparison(
                maze_copy, agent_start, target_start,
                evasive, wall_schedule, lookahead, threshold,
            )
            continue

        elif choice == "5":
            evasive, wall_schedule, lookahead, threshold = _prompt_scenario(
                maze, agent_start, target_start
            )
            print(f"\n  Scenario updated.  Target: {'Evasive' if evasive else 'Random'}")
            time.sleep(0.8)
            continue

        elif choice == "6":
            _show_tutorial()
            continue

        elif choice == "0":
            print("\nGoodbye! 🎯\n")
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
                 agent_start, target_start) = setup_new_session()
                evasive       = True
                wall_schedule = []
                lookahead     = 5
                threshold     = 3
                maze_copy     = []
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
    print(_center_ansi("📚  PURSUIT TUTORIAL — DYNAMIC / PAC-MAN MODE  📚", _TW))
    print("═" * _TW)
    print(
        "\n  A pursuer (►) must reach a moving target (◆) before the step\n"
        "  budget runs out.  The target moves one cell per tick.  Dynamic\n"
        "  walls (▪) can appear mid-run to simulate an unstable world.\n"
    )
    entries = [
        (
            "1. Naive Recalculation  (baseline)",
            "  Runs full A* on every single tick.  The path is always optimal\n"
            "   for the target's CURRENT position.  Replans = Steps (ratio 1.0).\n"
            "   Use as your reference: any smarter strategy should have ratio < 1.\n"
            f"   {C_BIGO}T:O(steps·(V+E)logV)  S:O(V){C_END}",
        ),
        (
            "2. Dynamic Repair  (D* Lite inspired)",
            "  Caches the path.  Replan is triggered only if:\n"
            "    (a) Target has moved > threshold cells from cached goal.\n"
            "    (b) A new wall now blocks a cached path cell.\n"
            "  The replans/steps ratio measures amortised replanning cost.\n"
            "  On slow-moving targets: ratio ≈ 0.1  (90% computation saved).\n"
            f"   {C_BIGO}T:O(repairs·(V+E)logV)  S:O(V){C_END}",
        ),
        (
            "3. Greedy Intercept  (velocity projection)",
            "  Predicts target position N steps ahead using its current velocity.\n"
            "  Runs A* toward the predicted intercept — NOT the current position.\n"
            f"  {C_INTERCEPT}✦{C_END} marks the intercept target on the maze.\n"
            "  On directional evaders: pursuer cuts across to intercept corridor.\n"
            "  On random walkers: prediction is wrong, degrades to Naive behaviour.\n"
            f"   {C_BIGO}T:O(replans·(V+E)logV)  S:O(V){C_END}",
        ),
    ]
    for title, desc in entries:
        print(f"\n  {C_PATH}{title}:{C_END}")
        print(f"   {desc}")

    print("\n" + "═" * _TW)
    print(
        f"\n  Legend:  "
        f"{C_PATH}►{C_END}=agent   "
        f"{C_TARGET}◆{C_END}=target   "
        f"{C_INTERCEPT}✦{C_END}=intercept   "
        f"{C_DOT}·{C_END}=planned path   "
        f"{C_WALL}▪{C_END}=dynamic wall"
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
