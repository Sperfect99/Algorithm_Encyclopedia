"""
treasure_solver2.py — TSP / Treasure Hunt module entry point.

Interactive session for the three TSP algorithms (Nearest Neighbour,
Brute Force, Genetic Algorithm) visualised on a live maze grid.
Includes Report Card comparison, Duel overlay, Benchmark, and Autopsy.
"""

from __future__ import annotations

import time
import os
from typing import NamedTuple

from treasure_gen import generate_treasure_map, MAZE_SIZES

from core.types        import TreasureRunResult, _StepRecord
from ui.theme          import (                                # noqa: F401,F403
    C_WALL, C_DOT, C_BACK, C_HEAD, C_PATH, C_START, C_MUD, C_END,
    C_DUEL2, C_BIGO, C_TREASURE, C_COLLECTED, C_GA_LIVE, C_STAT,
    ansi_enable_windows,
)
from ui.terminal_utils import (
    clear_screen, _strip_ansi, _visual_width, _center_ansi,
    _check_terminal_size, _term_width, flush_stdin,
)
from ui.renderer       import render_tsp
from ui.animation      import run_tsp_animation

# ── Phase 4: pure algorithm generators ───────────────────────────────────────
from algorithms.tsp import (
    nearest_neighbour_gen,
    brute_force_gen,
    genetic_algorithm_gen,
)

ansi_enable_windows()

# ===========================================================================
# ── RENDERING CONSTANTS ───────────────────────────────────────────────────────
# ===========================================================================
# Cell rendering and colours all live in ui/ now.

_BENCH_DELAY: float = 0.0
_BENCH_SKIP:  int   = 999_999

_SPEED_PRESETS: dict[str, tuple[float, int]] = {
    "1": (0.15, 1),
    "2": (0.05, 1),
    "3": (0.0,  3),
    "4": (0.0,  _BENCH_SKIP),
}


# ===========================================================================
# ── ALGORITHM METADATA ────────────────────────────────────────────────────────
# ===========================================================================

_ALGO_NAMES: dict[str, str] = {
    "1": "Nearest Neighbour (Greedy)",
    "2": "Brute Force (Exact Optimal)",
    "3": "Genetic Algorithm",
}

_ALGO_BIG_O: dict[str, str] = {
    "Nearest Neighbour (Greedy)":
        "T:O(N²·V) precomp + O(N) decisions  S:O(V)  ▸ greedy min-cost selection",
    "Brute Force (Exact Optimal)":
        "T:O(N!·N) enumeration  S:O(N!)  ▸ itertools.permutations — guaranteed optimal",
    "Genetic Algorithm":
        "T:O(G·P·N) + O(N²) 2-opt  S:O(P·N)  ▸ OX1 crossover + swap mutation + polish",
}

_ALGO_VERDICTS: dict[str, str] = {
    "Nearest Neighbour (Greedy)": (
        "Always rushes to the CLOSEST unvisited treasure — O(1) decision per stop.\n"
        "   Minimises 'Time to First Treasure' at the cost of a suboptimal total tour\n"
        "   (can be up to 25% longer than optimal on certain maze configurations).\n"
        "   The canonical greedy-algorithm lesson: locally perfect, globally flawed."
    ),
    "Brute Force (Exact Optimal)": (
        "Checks all N! orderings and picks the mathematically shortest tour.\n"
        "   Guaranteed optimal — but computation explodes factorially:\n"
        "   7! = 5 040 perms,  9! = 362 880,  12! = 479 001 600 (intractable).\n"
        "   Note the 'think phase' delay before the first move — classic OFFLINE planner."
    ),
    "Genetic Algorithm": (
        "Evolves a population of candidate tours over hundreds of generations.\n"
        "   OX1 crossover preserves relative order; swap mutation escapes local minima.\n"
        "   Post-convergence 2-opt polishing sharpens the best chromosome further.\n"
        "   The live maze overlay makes evolutionary computation tangible and beautiful."
    ),
}


# ===========================================================================
# ── AUTOPSY RECORDING STATE ───────────────────────────────────────────────────
# ===========================================================================

_ACTIVE_RECORDING: list[_StepRecord] | None = None


def _start_recording() -> None:
    """Activate the autopsy recording buffer for the next algorithm run."""
    global _ACTIVE_RECORDING
    _ACTIVE_RECORDING = []


def _stop_recording() -> list[_StepRecord]:
    """Deactivate the recording buffer and return captured deltas."""
    global _ACTIVE_RECORDING
    captured          = _ACTIVE_RECORDING if _ACTIVE_RECORDING is not None else []
    _ACTIVE_RECORDING = None
    return captured


# ===========================================================================
# ── DISPATCH — creates generator + drives animation ───────────────────────────
# ===========================================================================

def _dispatch(
    choice:      str,
    maze:        list[list[int | str]],
    points:      list[tuple[int, int]],
    dist_matrix: list[list[float]],
    cost_matrix: list[list[float]],
    path_matrix: list[list],
    delay:       float,
    skip_frames: int,
) -> TreasureRunResult:
    """
    Create the appropriate TSP generator and drive it via run_tsp_animation().

    This is the clean MVC bridge:
      - Controller (this function) selects the generator and wires it up.
      - Algorithm (algorithms/tsp.py) owns all math — yields pure state dicts.
      - Animation driver (ui/animation.py) owns rendering and timing.

    The dist_matrix is included in the signature for API compatibility with
    run_duel() and run_benchmark() — the generators only need cost_matrix
    and path_matrix for their computations.
    """
    _gen_map = {
        "1": nearest_neighbour_gen,
        "2": brute_force_gen,
        "3": genetic_algorithm_gen,
    }
    if choice not in _gen_map:
        raise KeyError(f"Unknown algorithm choice: {choice!r}")

    gen = _gen_map[choice](points, cost_matrix, path_matrix)

    return run_tsp_animation(
        gen           = gen,
        maze          = maze,
        path_matrix   = path_matrix,
        skip_frames   = skip_frames,
        delay         = delay,
        algo_name     = _ALGO_NAMES[choice],
        active_recording = None if skip_frames >= 999_999 else _ACTIVE_RECORDING,
    )


# ===========================================================================
# ── REPORT CARD ───────────────────────────────────────────────────────────────
# ===========================================================================

def show_report_card(
    algo_name:      str,
    result:         TreasureRunResult,
    terrain_active: bool,
) -> None:
    """Display a structured post-run statistics panel."""
    W       = 72
    bigo    = _ALGO_BIG_O.get(algo_name, "")
    verdict = _ALGO_VERDICTS.get(algo_name, "")
    failed  = result.total_steps == float('inf')

    print("\n" + "═" * W)
    print(f"📊  TREASURE HUNT REPORT CARD — {algo_name}".center(W))
    print("═" * W)

    if failed:
        print(f"  {C_HEAD}Result              : ❌  INCOMPLETE — not all treasures found.{C_END}")
        print(f"  {'Collected':<26}: {result.n_collected} / {result.n_treasures}")
    else:
        print(f"  {'Treasures Collected':<26}: {result.n_collected} / {result.n_treasures}  ✅")
        print(f"  {'Total Tour Steps':<26}: {int(result.total_steps)}")
        if algo_name == "Nearest Neighbour (Greedy)":
            first_note = f"   ← KEY METRIC: NN always picks nearest first{C_END}"
        elif algo_name == "Brute Force (Exact Optimal)":
            first_note = f"   ← may be HIGH by design (global route skips nearby){C_END}"
        elif algo_name == "Genetic Algorithm":
            first_note = f"   ← GA optimises total cost, not urgency{C_END}"
        else:
            first_note = f"{C_END}"
        print(
            f"  {C_STAT}{'Time to First Treasure':<26}: {result.time_to_first} steps"
            f"{first_note}"
        )
        if terrain_active and result.tour_cost != result.total_steps:
            print(f"  {'Weighted Tour Cost':<26}: {result.tour_cost}  (mud=3, road=1)")
            mud_cells = (result.tour_cost - int(result.total_steps)) // 2
            if mud_cells > 0:
                print(f"  {'  └ mud cells on tour':<26}: ≈{mud_cells}")

        order_str = "S → " + " → ".join(f"T{t}" for t in result.tour_order)
        print(f"  {'Tour Order':<26}: {order_str}")

    print(f"  {'Compute Time':<26}: {result.compute_time * 1000:.2f} ms")

    if bigo:
        print(f"  {C_BIGO}{'Complexity':<26}: {bigo}{C_END}")

    if verdict:
        print("─" * W)
        print(f"  💡 {verdict}")

    print("═" * W)


# ===========================================================================
# ── ALGORITHM AUTOPSY ─────────────────────────────────────────────────────────
# ===========================================================================

def run_autopsy(
    initial_maze: list[list[int | str]],
    recording:    list[_StepRecord],
    algo_name:    str,
) -> None:
    """
    Interactive step-by-step replay of a completed algorithm run.

    Navigation: ENTER=next  b=back  <N>=jump  q=quit

    Uses render_tsp() (imported from ui.renderer) so that TSP-domain cell
    values ('T', 'c', 'g') are rendered with correct colours during replay.
    """
    if not recording:
        print(f"\n  (No steps recorded for {algo_name}.)")
        input(f"  Press {C_PATH}ENTER{C_END} to continue…")
        return

    total = len(recording)
    maze  = [row[:] for row in initial_maze]
    pos   = 0

    def _rebuild_to(target: int) -> None:
        nonlocal pos
        for ri, row in enumerate(initial_maze):
            for ci, val in enumerate(row):
                maze[ri][ci] = val
        pos = 0
        for i in range(target):
            rec = recording[i]
            maze[rec.r][rec.c] = rec.new_cell
        pos = target

    clear_screen()
    print(
        f"\n{C_HEAD}⏮  TOUR AUTOPSY — {algo_name}{C_END}\n"
        f"  {total} steps recorded.\n"
        f"  ENTER=next  b=back  <number>=jump  q=quit\n"
    )
    time.sleep(0.8)

    while True:
        saved  = None
        r_head = c_head = -1

        if pos > 0:
            rec    = recording[pos - 1]
            r_head, c_head = rec.r, rec.c
            if maze[r_head][c_head] not in {'S', 'E', 'T', 'c'}:
                saved = maze[r_head][c_head]
                maze[r_head][c_head] = '@'

        hud_text = (
            recording[pos - 1].hud if pos > 0
            else f"{algo_name} — start of run (no steps applied yet)"
        )
        nav_line = f"⏮  Autopsy: step {pos}/{total}  [ENTER=next  b=back  <N>=jump  q=quit]"
        render_tsp(maze, f"{hud_text}\n{nav_line}")

        if saved is not None:
            maze[r_head][c_head] = saved

        raw = input("  → ").strip().lower()

        if raw == 'q':
            break
        elif raw == 'b':
            if pos > 0:
                rec = recording[pos - 1]
                maze[rec.r][rec.c] = rec.prev_cell
                pos -= 1
        elif raw == '':
            if pos < total:
                rec = recording[pos]
                maze[rec.r][rec.c] = rec.new_cell
                pos += 1
        else:
            try:
                _rebuild_to(max(0, min(total, int(raw))))
            except ValueError:
                pass   # non-integer — nav_line re-renders on next loop iteration


# ===========================================================================
# ── DUEL — SIDE-BY-SIDE TOUR COMPARISON ──────────────────────────────────────
# ===========================================================================

def run_duel(
    original_maze:  list[list[int | str]],
    points:         list[tuple[int, int]],
    dist_matrix:    list[list[float]],
    cost_matrix:    list[list[float]],
    path_matrix:    list[list],
    maze1_result:   list[list[int | str]],
    result1:        TreasureRunResult,
    algo1_name:     str,
    terrain_active: bool,
) -> None:
    """
    Head-to-head tour-path comparison between two algorithms.

    Challenger 2 is run in instant mode (no animation).  The overlay grid
    marks:
        Green 1  — cells on Challenger 1's path only
        Blue  2  — cells on Challenger 2's path only
        Red   *  — shared cells (both algorithms passed through)
    """
    clear_screen()
    rows, cols = len(original_maze), len(original_maze[0])
    print("\n" + "═" * 64)
    print("⚔️   TOUR DUEL — HEAD-TO-HEAD PATH COMPARISON".center(64))
    print("═" * 64)
    _c1_steps = "FAILED" if result1.total_steps == float('inf') else str(int(result1.total_steps))
    print(
        f"  {C_PATH}Challenger 1{C_END} : {algo1_name}"
        f"  ({_c1_steps} steps, cost {result1.tour_cost})"
    )
    print(f"\n  Select {C_DUEL2}Challenger 2{C_END}:\n")
    for key, name in _ALGO_NAMES.items():
        print(f"  {key}. {name}")
    print()

    while True:
        choice2 = input("  Challenger 2 (1-3): ").strip()
        if choice2 in _ALGO_NAMES:
            break
        print("  Invalid — enter 1, 2, or 3.")

    algo2_name = _ALGO_NAMES[choice2]

    # Rebuild treasure positions on a clean copy.
    maze2 = [row[:] for row in original_maze]
    for r, c in points[1:]:
        maze2[r][c] = 'T'

    print(f"\n  ⏳ Running {algo2_name} (instant mode)…")
    result2 = _dispatch(
        choice2, maze2, points,
        dist_matrix, cost_matrix, path_matrix,
        _BENCH_DELAY, _BENCH_SKIP,
    )

    # Build overlay grid.
    output: list[str] = []
    shared_n = only1_n = only2_n = 0

    # TSP cell render needs the TSP_CELL_RENDER for walls/endpoints.
    _WALL_GLYPH = f"{C_WALL}█{C_END}"
    _S_GLYPH    = f"{C_START}S{C_END}"
    _E_GLYPH    = f"{C_START}E{C_END}"
    _T_GLYPH    = f"{C_TREASURE}T{C_END}"
    _OPEN_GLYPH = " "

    for ri in range(rows):
        parts: list[str] = []
        for ci in range(cols):
            orig = original_maze[ri][ci]
            p1   = maze1_result[ri][ci] == 'P'
            p2   = maze2[ri][ci]        == 'P'

            if orig == 1:
                parts.append(_WALL_GLYPH)
            elif orig == 'S':
                parts.append(_S_GLYPH)
            elif orig == 'E':
                parts.append(_E_GLYPH)
            elif orig == 'T':
                parts.append(_T_GLYPH)
            elif p1 and p2:
                parts.append(f"{C_HEAD}*{C_END}")
                shared_n += 1
            elif p1:
                parts.append(f"{C_PATH}1{C_END}")
                only1_n  += 1
            elif p2:
                parts.append(f"{C_DUEL2}2{C_END}")
                only2_n  += 1
            else:
                parts.append(_OPEN_GLYPH)
        output.append("".join(parts))

    clear_screen()
    print(f"\n⚔️  DUEL: {C_PATH}{algo1_name}{C_END}  vs  {C_DUEL2}{algo2_name}{C_END}\n")
    print("\n".join(output))

    W  = 64
    f1 = result1.total_steps == float('inf')
    f2 = result2.total_steps == float('inf')

    def _fmt(val: float, failed: bool) -> str:
        return "FAILED" if failed else str(int(val))

    print("\n" + "─" * W)
    print(f"  {'Metric':<24} {algo1_name:<20} {algo2_name:<18}")
    print("─" * W)
    print(f"  {'Total Steps':<24} {_fmt(result1.total_steps,f1):<20} {_fmt(result2.total_steps,f2):<18}")
    print(f"  {'Time to First':<24} {result1.time_to_first:<20} {result2.time_to_first:<18}")
    if terrain_active:
        print(f"  {'Tour Cost':<24} {result1.tour_cost:<20} {result2.tour_cost:<18}")
    t1ms = f"{result1.compute_time * 1000:.2f} ms"
    t2ms = f"{result2.compute_time * 1000:.2f} ms"
    print(f"  {'Compute Time':<24} {t1ms:<20} {t2ms:<18}")
    print("─" * W)
    print(
        f"  {C_PATH}1{C_END}={algo1_name[:16]} only ({only1_n})   "
        f"{C_DUEL2}2{C_END}={algo2_name[:16]} only ({only2_n})   "
        f"{C_HEAD}*{C_END}=shared ({shared_n})"
    )
    print("─" * W)

    # Declare a winner on total steps.
    if not f1 and not f2:
        if result1.total_steps < result2.total_steps:
            diff = int(result2.total_steps) - int(result1.total_steps)
            print(f"\n  🏆 {C_PATH}{algo1_name} has the SHORTER TOTAL TOUR{C_END}"
                  f" by {diff} steps.")
        elif result2.total_steps < result1.total_steps:
            diff = int(result1.total_steps) - int(result2.total_steps)
            print(f"\n  🏆 {C_DUEL2}{algo2_name} has the SHORTER TOTAL TOUR{C_END}"
                  f" by {diff} steps.")
        else:
            print(f"\n  🤝 DEAD TIE on total tour length!")

        if result1.time_to_first < result2.time_to_first:
            print(f"  ⚡ {C_PATH}{algo1_name} reached first treasure FASTER{C_END}"
                  f" ({result1.time_to_first} vs {result2.time_to_first} steps).")
        elif result2.time_to_first < result1.time_to_first:
            print(f"  ⚡ {C_DUEL2}{algo2_name} reached first treasure FASTER{C_END}"
                  f" ({result2.time_to_first} vs {result1.time_to_first} steps).")

    print("─" * W)


# ===========================================================================
# ── BENCHMARK ─────────────────────────────────────────────────────────────────
# ===========================================================================

def run_benchmark(
    original_maze:  list[list[int | str]],
    points:         list[tuple[int, int]],
    dist_matrix:    list[list[float]],
    cost_matrix:    list[list[float]],
    path_matrix:    list[list],
    terrain_active: bool,
) -> None:
    """
    Run all applicable algorithms on identical maze copies and compare.

    Animation and autopsy recording are forcibly disabled for pure CPU timing.
    Brute Force is skipped if N > 8.
    """
    clear_screen()
    N = len(points) - 1
    print("\n" + "═" * 80)
    print("⏳  TREASURE BENCHMARK — ALL ALGORITHMS, SAME MAZE  ⏳".center(80))
    print("═" * 80)
    print(f"  Maze: {len(original_maze)} × {len(original_maze[0])}   "
          f"Treasures: {N}   Terrain: {'ON' if terrain_active else 'OFF'}\n")

    algorithms = [
        ("1", "Nearest Neighbour"),
        ("3", "Genetic Algorithm"),
    ]
    if N <= 8:
        algorithms.insert(1, ("2", "Brute Force"))
    else:
        print(f"  ⚠️  Brute Force skipped (N={N} > 8, N! too large).\n")

    print("⏳ Running…\n")
    time.sleep(0.3)

    results: list[tuple[str, TreasureRunResult]] = []

    for choice, display_name in algorithms:
        maze_copy = [row[:] for row in original_maze]
        for r, c in points[1:]:
            maze_copy[r][c] = 'T'

        result = _dispatch(
            choice, maze_copy, points,
            dist_matrix, cost_matrix, path_matrix,
            _BENCH_DELAY, _BENCH_SKIP,
        )
        results.append((display_name, result))
        status = "FAILED" if result.total_steps == float('inf') else f"{int(result.total_steps)} steps"
        print(f"  ✔  {display_name:<30} {status}")

    clear_screen()
    W = 80
    print("\n" + "═" * W)
    print("🏆  BENCHMARK RESULTS — TREASURE HUNT TSP  🏆".center(W))
    print("═" * W)
    if terrain_active:
        print(
            f"| {'ALGORITHM':<22} | {'TOUR STEPS':<11} | {'1ST TREAS.':<11}"
            f" | {'COST':<8} | {'CPU (ms)':<10} |"
        )
    else:
        print(
            f"| {'ALGORITHM':<22} | {'TOUR STEPS':<11} | {'1ST TREAS.':<11}"
            f" | {'CPU (ms)':<10} |"
            f"  ← no terrain: COST = STEPS"
        )
    print("-" * W)

    for name, r in sorted(results, key=lambda x: x[1].total_steps):
        steps_s = str(int(r.total_steps)) if r.total_steps != float('inf') else "FAILED"
        first_s = str(r.time_to_first)    if r.total_steps != float('inf') else "—"
        cost_s  = str(r.tour_cost)        if r.total_steps != float('inf') else "—"
        if terrain_active:
            print(
                f"| {name:<22} | {steps_s:<11} | {first_s:<11}"
                f" | {cost_s:<8} | {r.compute_time * 1000:<10.2f} |"
            )
        else:
            print(
                f"| {name:<22} | {steps_s:<11} | {first_s:<11}"
                f" | {r.compute_time * 1000:<10.2f}         |"
            )

    print("═" * W)
    if N <= 8:
        planning_note = "Brute Force / GA invest in route planning; total tour wins."
    else:
        planning_note = "GA invests in route planning; total tour typically beats Nearest Neighbour."
    print(
        f"\n  {C_STAT}📊 KEY INSIGHT:{C_END}  Compare '1st Treas.' vs 'Tour Steps'.\n"
        f"  Nearest Neighbour rushes to first treasure; total tour may be longer.\n"
        f"  {planning_note}\n"
        f"  This is the core greedy-vs-optimal tradeoff in NP-hard optimisation."
    )


# ===========================================================================
# ── TUTORIAL ──────────────────────────────────────────────────────────────────
# ===========================================================================

def show_tutorial() -> None:
    """Display educational descriptions of TSP and all three algorithms."""
    clear_screen()
    print("\n" + "═" * 70)
    print("📚  TREASURE HUNT TUTORIAL — TSP ON A GRID  📚".center(70))
    print("═" * 70)

    print(
        f"\n{C_START}What is TSP?{C_END}\n"
        "   The Traveling Salesperson Problem asks: given N cities, find the\n"
        "   shortest route visiting all of them.  It is NP-hard — no\n"
        "   known polynomial-time exact algorithm exists for general inputs.\n"
        "   Here, 'cities' are treasure cells; distance = terrain-weighted cost.\n"
        f"   {C_STAT}Implementation note:{C_END} We use the OPEN-PATH variant — the agent\n"
        "   starts at S, visits every treasure, and stops at the last one.\n"
        "   The classic academic TSP is a closed cycle back to S; costs differ.\n"
        "   We compare an exact solver (Brute Force), a greedy heuristic\n"
        "   (Nearest Neighbour), and an evolutionary method (Genetic Algorithm)."
    )

    print(
        f"\n{C_START}Why Two Metrics?{C_END}\n"
        f"   {C_STAT}Total Tour Steps{C_END}  — Cells walked on the entire journey (hop count).\n"
        f"                        Lower = more efficient overall route.\n"
        f"   {C_STAT}Weighted Tour Cost{C_END} — Terrain-weighted cost (mud=3, road=1).\n"
        f"                        This is what GA and Brute Force actually optimise.\n"
        f"   {C_STAT}Time to First Treasure{C_END}  — Hop count before first collection.\n"
        "                        Always in hops, never terrain-weighted.\n"
        "                        Models urgency: get the nearest item fast.\n"
        f"   {C_DIM}Note: 'Steps' and 'Time to First' use hop count (terrain-blind).\n"
        f"   'Weighted Cost' includes terrain. Compare carefully.{C_END}"
    )

    entries = [
        (
            "1. Nearest Neighbour (Greedy)",
            f"Set + Cost Matrix (O(1) lookup)  |  space O(N+V)\n"
            f"   Pre-computation: O(N²·V) — build full Dijkstra cost matrix.\n"
            f"   Decision loop : O(N) iterations × O(N) 'min' scan = O(N²) total.\n"
            f"   Path quality  : Typically 15-25% worse than optimal (no lookahead).\n"
            f"   Starting-node sensitivity: always starts from S (the depot).\n"
            f"   On some layouts, a different start node would give a shorter tour.\n"
            f"   This is NN's key theoretical weakness vs. GA and Brute Force.\n"
            f"   {C_STAT}Best metric  : Time to First Treasure (always picks nearest).{C_END}",
        ),
        (
            "2. Brute Force (Exact Optimal)",
            f"itertools.permutations iterator  |  space O(N!)\n"
            f"   Complexity   : O(N! × N) — grows catastrophically with N.\n"
            f"   Path quality : Guaranteed optimal — mathematically proven.\n"
            f"   Think phase  : ALL computation happens BEFORE the first move.\n"
            f"   {C_STAT}Best metric  : Total Tour Steps (guaranteed minimum).{C_END}\n"
            f"   Disabled for N>8 (9! = 362 880 perms; 12! = 479 million).",
        ),
        (
            "3. Genetic Algorithm",
            f"list of chromosomes (permutations)  |  space O(P×N)\n"
            f"   Chromosome   : list of N treasure indices — one tour ordering.\n"
            f"   Fitness      : weighted BFS cost of the complete tour.\n"
            f"   Selection    : Tournament (k=3-5) — balances pressure vs diversity.\n"
            f"   Crossover    : OX1 (Ordered) — preserves relative visit order.\n"
            f"   Mutation     : Random swap — 18% rate, escapes local minima.\n"
            f"   Elitism      : Always keep the best chromosome unchanged.\n"
            f"   2-opt polish : Post-convergence edge-swap refinement pass.\n"
            f"   {C_STAT}Best metric  : Near-optimal Total Tour (not always exact).{C_END}\n"
            f"   Non-deterministic: every run on the same maze gives a different\n"
            f"   tour order and cost — this is expected GA behaviour, not a bug.",
        ),
        (
            "Cost Matrix  (lives in treasure_gen.py)",
            f"All three algorithms share one Dijkstra cost matrix computed ONCE.\n"
            f"   N+1 Dijkstra runs (from S and each T), each O((V+E)logV) — total O(N·(V+E)logV).\n"
            f"   dist_matrix[i][j] = weighted terrain cost from point i to point j.\n"
            f"   cost_matrix[i][j] = weighted terrain cost (mud=3, road=1).\n"
            f"   path_matrix[i][j] = actual list of cells to walk for animation.\n"
            f"   Algorithms use cost_matrix for decisions, path_matrix for display.",
        ),
        (
            "Why is TSP NP-hard?",
            f"Even with precomputed pairwise distances, the number of distinct\n"
            f"   tours grows as (N-1)!/2 — faster than any polynomial.\n"
            f"   Current best exact algorithms (Concorde) solve ~100 000-city\n"
            f"   instances but use years of CPU time.  For practical use:\n"
            f"   heuristics (NN) and metaheuristics (GA, simulated annealing)\n"
            f"   find good-enough solutions in polynomial time.",
        ),
    ]

    for title, desc in entries:
        print(f"\n{C_TREASURE}{title}:{C_END}")
        print(f"   {desc}")

    print("\n" + "═" * 70)
    input(f"\n👉 Press {C_PATH}ENTER{C_END} to return to the Main Menu…")


# ===========================================================================
# ── SETUP  (UI layer only — generation delegated to treasure_gen.py) ──────────
# ===========================================================================

def _prompt_speed() -> tuple[float, int]:
    """Prompt for animation speed; return (delay_seconds, skip_frames)."""
    print("\nSelect animation speed:")
    print("  1. Slow    — every frame, 150 ms delay")
    print("  2. Normal  — every frame,  50 ms delay  (recommended)")
    print("  3. Fast    — every 3rd frame, no delay")
    print("  4. Instant — no animation (results only)")
    while True:
        choice = input("Speed (1-4): ").strip()
        if choice in _SPEED_PRESETS:
            return _SPEED_PRESETS[choice]
        print("  Please enter 1, 2, 3, or 4.")


def setup_treasure_maze() -> tuple[
    list[list[int | str]],   # maze
    list[tuple[int, int]],   # points [S, T1..TN]
    list[list[float]],       # dist_matrix
    list[list[float]],       # cost_matrix
    list[list],              # path_matrix
    float,                   # delay
    int,                     # skip_frames
    bool,                    # terrain_active
    int,                     # n_treasures
]:
    """
    Full setup wizard: prompt user for all parameters, then delegate map
    generation to 'generate_treasure_map()' from 'treasure_gen.py'.

    V2.0 responsibilities (UI only — unchanged from V1.2):
      • Prompt: maze complexity level
      • Prompt: number of treasures
      • Prompt: animation speed
      • Prompt: terrain on/off
      • Print progress messages during generation
      • Handle RuntimeError from generate_treasure_map gracefully

    Map creation responsibilities (treasure_gen.py — unchanged):
      • generate_maze() + add_terrain()
      • scatter_treasures()
      • build_distance_matrix()
      • Connectivity verification + silent retry
    """
    clear_screen()
    _SIZE_LABELS = {
        0: "tiny",   1: "tiny",   2: "small",  3: "small",
        4: "medium", 5: "medium", 6: "large",  7: "large",
        8: "huge",   9: "huge",  10: "massive",
    }
    print("\n" + "═" * 66)
    print("🗺️   TREASURE HUNT SETUP  🗺️".center(66))
    print("═" * 66)
    print("\nSelect Maze Complexity Level:\n")
    for lvl, (r, c) in MAZE_SIZES.items():
        label = _SIZE_LABELS[lvl]
        print(f"  {lvl:>2}  →  {r:>2} × {c:<3} grid  ({label})")

    print()
    while True:
        try:
            comp = int(input("Enter level (0-10): "))
            if 0 <= comp <= 10:
                break
            print("  Please enter 0–10.")
        except ValueError:
            print("  Invalid input — enter an integer.")

    maze_rows, maze_cols = MAZE_SIZES[comp]
    _check_terminal_size(maze_rows, maze_cols)

    delay, skip_frames = _prompt_speed()

    # ── Treasure count ────────────────────────────────────────────────────
    max_t = 9 if comp >= 5 else 7 if comp >= 3 else 5
    print(f"\nHow many treasures? (1-{max_t} recommended for this maze size)")
    print(f"  {C_HEAD}Note:{C_END} Brute Force is disabled for N > 8.")
    while True:
        try:
            n_t = int(input(f"Treasures (1-{max_t}): "))
            if 1 <= n_t <= max_t:
                break
            print(f"  Please enter 1 to {max_t}.")
        except ValueError:
            print("  Invalid input — enter a whole number.")

    # ── Terrain option ────────────────────────────────────────────────────
    terrain_active = False
    if comp >= 3:
        print(
            f"\n{C_MUD}Weighted Terrain:{C_END} Mud patches (~) cost 3× to traverse.\n"
            "  Cost-aware algorithms (all three) will prefer road over mud.\n"
            "  'Tour Cost' in report cards reflects terrain weight."
        )
        while True:
            t_ans = input("Add mud terrain? (y/n): ").strip().lower()
            if t_ans in {'y', 'yes', 'n', 'no'}:
                break
        terrain_active = t_ans in {'y', 'yes'}

    # ── Generation (fully delegated) ──────────────────────────────────────
    print("\n⏳ Generating maze and placing treasures… Please wait!")

    try:
        maze, points, dist_matrix, cost_matrix, path_matrix = generate_treasure_map(
            complexity=comp,
            num_treasures=n_t,
            terrain_active=terrain_active,
        )
    except RuntimeError as exc:
        # Extremely rare — reduce treasure count and try once more.
        print(f"\n  ⚠️  {exc}")
        n_t = max(1, n_t // 2)
        print(f"  Reducing to {n_t} treasure(s) and retrying…")
        try:
            maze, points, dist_matrix, cost_matrix, path_matrix = generate_treasure_map(
                complexity=comp,
                num_treasures=n_t,
                terrain_active=terrain_active,
            )
        except RuntimeError as exc2:
            print(f"\n  ❌ Generation failed after retry: {exc2}")
            print("  Please restart and choose a lower complexity or fewer treasures.")
            raise EOFError from exc2   # surfaces cleanly via the outer handler

    actual_n = len(points) - 1   # may differ if generate_treasure_map adjusted
    print(f"  ✔ Maze generated: {len(maze)} × {len(maze[0])}")
    print(f"  ✔ {actual_n} treasure(s) placed.")
    print(f"  ✔ Dijkstra cost matrix built ({len(points)} points).")
    time.sleep(0.3)

    return (
        maze, points, dist_matrix, cost_matrix, path_matrix,
        delay, skip_frames, terrain_active, actual_n,
    )


# ===========================================================================
# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
# ===========================================================================

def _main_loop() -> None:
    """
    Inner session loop.  Wrapped by main() for clean KeyboardInterrupt handling.

    V2.0 changes vs V1.2:
        Algorithm generators imported from algorithms/tsp.py.
        _dispatch() creates a generator and calls run_tsp_animation() instead
        of calling a monolithic solve_* function.
        run_autopsy() calls render_tsp() (from ui.renderer) instead of the
        old local render() function.

    Post-run menu: [a]utopsy  [d]uel  ENTER=done  (loops until bare ENTER).
    Session state: last_result, last_maze_after, last_algo_name, recording —
    all reset on new maze.
    """
    (my_maze, points, dist_matrix, cost_matrix, path_matrix,
     delay, skip_frames, terrain_active, n_treasures) = setup_treasure_maze()

    last_result:     TreasureRunResult | None          = None
    last_maze_after: list[list[int | str]] | None      = None
    last_algo_name:  str                               = ""
    recording:       list[_StepRecord]                 = []

    while True:
        rows, cols  = len(my_maze), len(my_maze[0])
        terrain_lbl = f"{C_MUD}ON {C_END}" if terrain_active else f"{C_DOT}OFF{C_END}"
        _SPEED_NAMES = {"1": "Slow", "2": "Normal", "3": "Fast", "4": "Instant"}
        speed_lbl = next(
            (n for k, n in _SPEED_NAMES.items()
             if _SPEED_PRESETS[k] == (delay, skip_frames)),
            "Custom",
        )

        clear_screen()
        W = _term_width()
        print("\n" + "═" * W)
        print(_center_ansi("🗺️   TREASURE HUNT — TSP SOLVER   V2.0   🗺️", W))
        print("═" * W)
        print(
            f"  Maze: {rows} × {cols}  |  Speed: {C_DOT}{speed_lbl}{C_END}"
            f"  |  Treasures: {n_treasures}  |  Terrain: {terrain_lbl}"
        )
        print()
        print("  ─── TSP Algorithms ──────────────────────────────────────────")
        print(f"  1.  {C_DOT}Nearest Neighbour{C_END}   (Greedy, O(N²·V), fastest 1st find)")
        print(f"  2.  {C_PATH}Brute Force{C_END}         (Exact optimal, O(N!), N ≤ 8 only)")
        print(f"  3.  {C_GA_LIVE}Genetic Algorithm{C_END}   (Evolutionary, live tour mutation ★)")
        print()
        print("  ─── System ──────────────────────────────────────────────────")
        print("  4.  🏆  Benchmark        (all algorithms, same maze, comparison)")
        print("  5.  📚  Tutorial         (TSP theory, Big-O, algorithm deep-dives)")
        print("  0.  Exit")
        print("─" * W)
        print(
            f"  {C_STAT}Post-run menu:{C_END} [a]utopsy  [d]uel  ENTER=done"
        )
        print("─" * W)

        choice = input("Choose (0–5): ").strip()

        # ── System options ─────────────────────────────────────────────────

        if choice == "0":
            print(f"\n  {C_TREASURE}Goodbye — may your tours always be optimal! 🗺️{C_END}\n")
            break

        elif choice == "4":
            maze_bench = [row[:] for row in my_maze]
            for r, c in points[1:]:
                maze_bench[r][c] = 'T'
            run_benchmark(maze_bench, points, dist_matrix, cost_matrix,
                          path_matrix, terrain_active)
            input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")
            continue

        elif choice == "5":
            show_tutorial()
            continue

        elif choice in _ALGO_NAMES:
            algo_name = _ALGO_NAMES[choice]

            # Build a fresh maze copy with treasures in place.
            m_copy: list[list[int | str]] = [row[:] for row in my_maze]
            for r, c in points[1:]:
                m_copy[r][c] = 'T'

            # Save the maze state before running (for autopsy baseline).
            maze_before = [row[:] for row in m_copy]

            # Run algorithm with autopsy recording.
            _start_recording()
            try:
                result = _dispatch(
                    choice, m_copy, points,
                    dist_matrix, cost_matrix, path_matrix,
                    delay, skip_frames,
                )
            finally:
                recording = _stop_recording()

            last_result     = result
            last_maze_after = [row[:] for row in m_copy]   # snapshot — duel reads this; copy protects against future mutation
            last_algo_name  = algo_name

            # ── Report Card ───────────────────────────────────────────────
            from ui.terminal_utils import flush_stdin
            flush_stdin()
            input(f"\n👉 Press {C_PATH}ENTER{C_END} to see Report Card…")
            show_report_card(algo_name, result, terrain_active)

            # ── Post-run menu (loops until bare ENTER) ─────────────────────
            has_autopsy = bool(recording)
            has_duel    = result.total_steps != float('inf')

            opts: list[str] = []
            if has_autopsy:
                opts.append("[a]utopsy")
            if has_duel:
                opts.append("[d]uel")

            if opts:
                prompt_opts = "  ".join(opts) + "  ENTER=done"
                while True:
                    post = input(f"\n  ✨ Post-run: {prompt_opts}: ").strip().lower()

                    if post == '':
                        break

                    elif post in {'a', 'autopsy'} and has_autopsy:
                        run_autopsy(maze_before, recording, algo_name)

                    elif post in {'d', 'duel'} and has_duel:
                        run_duel(
                            my_maze, points,
                            dist_matrix, cost_matrix, path_matrix,
                            m_copy, result, algo_name, terrain_active,
                        )
                        input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

                    else:
                        print(f"  (Unrecognised — try: {prompt_opts})")
            else:
                input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

        else:
            print("  Invalid option — please try again.")
            time.sleep(0.5)
            continue

        # ── New-maze prompt ────────────────────────────────────────────────
        # ENTER or 'n' keeps the current map; 'y' generates a fresh one.
        while True:
            ans = input("\n  [ENTER/n] keep this map   [y] generate new map: ").strip().lower()
            if ans in {'y', 'yes'}:
                (my_maze, points, dist_matrix, cost_matrix, path_matrix,
                 delay, skip_frames, terrain_active, n_treasures) = setup_treasure_maze()
                last_result     = None
                last_maze_after = None
                last_algo_name  = ""
                recording       = []
                m_copy          = []
                maze_before     = []
                break
            elif ans in {'n', 'no', ''}:
                break
            else:
                print("  Please answer y or n.")


# ===========================================================================
# ── ENTRY POINT ───────────────────────────────────────────────────────────────
# ===========================================================================

def main() -> None:
    """
    Entry point.  Wraps the session loop with a clean handler for
    KeyboardInterrupt and EOFError.
    """
    try:
        _main_loop()
    except (KeyboardInterrupt, EOFError):
        print("\033[0m\n\n  Interrupted — goodbye! 🗺️\n")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Downstream pipe consumer closed early (e.g. `python ... | head`).
        # Flush stderr and exit silently — no traceback, exit code 0.
        import sys
        sys.stderr.close()
        sys.exit(0)
