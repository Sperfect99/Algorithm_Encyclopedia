"""
maze_controller.py — main entry point for the Classic Pathfinding module.

Handles maze generation, the main menu loop, algorithm dispatch, and all the
session state (fog mode, hypothesis scoring, terrain, etc.).

What lives here:
    _dispatch_algorithm()  — routes a menu choice to the right algorithm generator
    setup_new_maze()       — prompts for size/speed/terrain and builds a fresh maze
    main() / _main_loop()  — the actual interactive session loop

Everything else (rendering, algorithm logic, report cards, race/duel/benchmark)
is in separate modules. This file is the glue.
"""

from __future__ import annotations

import os
import time
from itertools import zip_longest
from typing import Callable

from maze_genV4 import generate_maze, add_terrain, MAZE_SIZES

from core.types        import RunResult, _StepRecord
from core.grid         import terrain_cost, DIRECTIONS, PASSABLE
from core.graph        import manhattan_distance
from ui.theme          import *                           # noqa: F401,F403
from ui.terminal_utils import (
    clear_screen, _strip_ansi, _visual_width, _center_ansi,
    _check_terminal_size, _term_width, flush_stdin,
)
ansi_enable_windows()

from ui.renderer  import render, render_split, render_heatmap, CELL_RENDER
from ui.animation import run_algorithm, animate_step

from algorithms.registry import (
    AlgorithmSpec, _REGISTRY,
    _ALGO_NAMES, _STEP_LABELS, _SPEC_BY_KEY, _MENU_SECTIONS,
    _get_generator,
    _ALGO_BIG_O, _ALGO_VERDICTS,
    _HOP_OPTIMAL, _COST_OPTIMAL, _MIGHT_FAIL,
)

from maze_views import (
    show_report_card,
    show_tutorial,
    _hypothesis_pre_run,
    _hypothesis_post_run,
)

from maze_modes import (
    run_autopsy,
    run_duel,
    run_race,
    run_benchmark,
)



# --- SPEED PRESETS ---

_BENCH_SKIP: int = 999_999   # instant mode sentinel — disables all animation

_SPEED_PRESETS: dict[str, tuple[float, int]] = {
    "1": (0.15,       1),   # Slow   — 150ms per frame
    "2": (0.05,       1),   # Normal — 50ms per frame
    "3": (0.0,        3),   # Fast   — every 3rd frame, no delay
    "4": (0.0,  999_999),   # Instant
}

_SPEED_NAMES: dict[str, str] = {"1": "Slow", "2": "Normal", "3": "Fast", "4": "Instant"}



# --- LIVE BIG-O HUD ---

# Using a list so helper functions can mutate it without needing `global`.
# Feels slightly hacky but cleaner than threading it through every call.
_ACTIVE_COMPLEXITY_SLOT: list[str] = [""]


def _set_active_complexity(algo_name: str) -> None:
    _ACTIVE_COMPLEXITY_SLOT[0] = _ALGO_BIG_O.get(algo_name, "")


def _clear_active_complexity() -> None:
    _ACTIVE_COMPLEXITY_SLOT[0] = ""



# --- AUTOPSY RECORDING STATE ---

_ACTIVE_RECORDING: list[_StepRecord] | None = None


def _start_recording() -> None:
    global _ACTIVE_RECORDING
    _ACTIVE_RECORDING = []


def _stop_recording() -> list[_StepRecord]:
    global _ACTIVE_RECORDING
    captured          = _ACTIVE_RECORDING if _ACTIVE_RECORDING is not None else []
    _ACTIVE_RECORDING = None
    return captured



# --- ALGORITHM DISPATCH ---

def _dispatch_algorithm(
    choice:      str,
    maze:        list[list[int | str]],
    delay:       float,
    skip_frames: int,
    fog:         set[tuple[int, int]] | None,
    visit_count: dict[tuple[int, int], int] | None,
) -> RunResult:
    """Route a menu choice string to the matching generator and run it.

    Also handles the large-maze warning for slow algorithms (driven by the
    AlgorithmSpec so we don't need any hardcoded algorithm names here).
    The generators themselves are UI-free — this is where the advisory lives.
    """
    vc: dict[tuple[int, int], int] = visit_count if visit_count is not None else {}
    spec      = _SPEC_BY_KEY[choice]
    algo_name = spec.display_name

    if spec.slow_maze_warning and skip_frames < _BENCH_SKIP:
        rows, cols  = len(maze), len(maze[0])
        total_cells = rows * cols
        if total_cells > spec.slow_warn_cells:
            render(
                maze,
                f"⚠️  {algo_name} on {rows}×{cols} ({total_cells} cells) may be slow.\n"
                "   Press ENTER to continue or Ctrl-C to abort.",
            )
            input()

    factory = _get_generator(spec.module_name)
    gen = factory(maze, fog=fog, visit_count=vc)  # type: ignore[operator]
    return run_algorithm(
        gen, maze, skip_frames, delay, algo_name,
        _ACTIVE_COMPLEXITY_SLOT, _ACTIVE_RECORDING,
        fog=fog,
    )



# --- SETUP HELPERS ---

def _prompt_speed() -> tuple[float, int]:
    """Ask the user how fast they want the animation."""
    print("\nSelect animation speed:")
    print("  1. Slow    — every frame, 150 ms delay  [PQ Inspector ✓]")
    print("  2. Normal  — every frame, 50 ms delay   [PQ Inspector ✓]  (default)")
    print("  3. Fast    — every 3rd frame, no delay  [PQ Inspector ✓]")
    print("  4. Instant — no animation, results only [PQ Inspector ✗ — heatmap still works]")
    while True:
        choice = input("Speed (1-4): ").strip()
        if choice in _SPEED_PRESETS:
            return _SPEED_PRESETS[choice]
        print("  Please enter 1, 2, 3, or 4.")


def setup_new_maze() -> tuple[list[list[int | str]], float, int, bool]:
    """Prompt for complexity/speed/terrain and return a freshly generated maze.

    Returns (maze, delay, skip_frames, terrain_active).
    """
    clear_screen()
    _SIZE_LABELS = {
        0: "tiny",   1: "tiny",   2: "small",  3:  "small",
        4: "medium", 5: "medium", 6: "large",  7:  "large",
        8: "huge",   9: "huge",  10: "massive",
    }
    print("Select Maze Complexity Level:\n")
    for lvl, (r, c) in MAZE_SIZES.items():
        label     = _SIZE_LABELS[lvl]
        race_note = ""
        if c * 2 + 7 > 120:
            race_note = f"  {C_RACE}(Race Mode needs ≥{c*2+7} cols){C_END}"
        print(f"  {lvl:>2}  →  {r:>2} × {c:<3} grid  ({label}){race_note}")

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

    terrain_active = False
    if comp >= 3:
        print(
            f"\n{C_MUD}Weighted Terrain:{C_END} Mud patches (~) cost 3× to traverse.\n"
            "  Cost-aware  : Dijkstra, A*, Bellman-Ford route around mud.\n"
            "  Cost-blind  : all others charge through it."
        )
        while True:
            t_ans = input("Add mud terrain? (y/n): ").strip().lower()
            if t_ans in {'y', 'yes', 'n', 'no'}:
                break
            print("  Please answer y or n.")
        if t_ans in {'y', 'yes'}:
            terrain_active = True

    print("\n⏳ Generating maze… Please wait!")
    maze = generate_maze(comp)
    if terrain_active:
        add_terrain(maze)

    return maze, delay, skip_frames, terrain_active



# --- MAIN LOOP ---

def main() -> None:
    """Entry point. Wraps the session loop with clean Ctrl-C / EOF handling
    so the terminal doesn't get a noisy traceback when running in class."""
    try:
        _main_loop()
    except (KeyboardInterrupt, EOFError):
        print("\033[0m\n\nInterrupted — goodbye! 🚀\n")


def _main_loop() -> None:
    """The actual interactive session. Extracted from main() so the exception
    handler in main() stays clean."""

    my_maze, delay, skip_frames, terrain_active = setup_new_maze()

    fog_mode:        bool                         = False
    hypothesis_mode: bool                         = False
    hyp_pts:         int                          = 0
    hyp_max_pts:     int                          = 0
    recording:       list[_StepRecord]            = []

    while True:
        rows, cols  = len(my_maze), len(my_maze[0])
        fog_lbl     = f"{C_BACK}ON {C_END}" if fog_mode      else f"{C_DOT}OFF{C_END}"
        terrain_lbl = f"{C_MUD}ON {C_END}"  if terrain_active else f"{C_DOT}OFF{C_END}"
        hyp_lbl     = (
            f"{C_HYP}ON{C_END}  Score: {C_HYP}{hyp_pts}/{hyp_max_pts} pts{C_END}"
            if hypothesis_mode else f"{C_DOT}OFF{C_END}"
        )

        speed_lbl = next(
            (n for k, n in _SPEED_NAMES.items()
             if _SPEED_PRESETS[k] == (delay, skip_frames)),
            "Custom",
        )

        W = _term_width()
        print("\n" + "═" * W)
        print(_center_ansi("🎓  MAZE SOLVER — THE PROFESSOR'S EDITION  V7  🎓", W))
        print("═" * W)
        print(
            f"  Maze: {C_BIGO}{rows}×{cols}{C_END}"
            f"  |  Speed: {C_DOT}{speed_lbl}{C_END}"
            f"  |  Terrain: {terrain_lbl}"
            f"  |  Fog: {fog_lbl}"
        )
        print()

        for _section_name, _specs in _MENU_SECTIONS.items():
            _bar = "─" * max(0, 49 - len(_section_name))
            print(f"  ─── {_section_name} {_bar}")
            for _sp in _specs:
                _pq = " [PQ✦]" if _sp.pq_inspector else ""
                print(f"  {_sp.key:>2}. {_sp.display_name:<20} ({_sp.menu_note}){_pq}")

        print("  ─── V5 Post-Run Modes ───────────────────────────────────")
        print("  (After each run: [h]eatmap  [a]utopsy  [d]uel  ENTER=done)")

        print("  ─── System ──────────────────────────────────────────────")
        print("  16. 🏆  Run Benchmark   (all algorithms at once)")
        print("  17. 📚  Tutorial        (data structures & complexity)")
        print(f"  18. 🌫️  Fog of War     — {fog_lbl}")
        print(f"  19. 🔮  Hypothesis     — {hyp_lbl}")
        print(f"  20. {C_RACE}🏎️  Race Mode{C_END}      (two algorithms, split-screen)")
        print(f"      🌿 Terrain        — {terrain_lbl}  (set at generation)")
        print(f"  {C_BIGO}  📐 Big-O HUD  — always active during algorithm runs{C_END}")
        print(f"  {C_PQ}  🗂  PQ Inspector — active for A*, Dijkstra, Greedy [PQ✦]{C_END}")
        print("  0.  Exit")
        print("─" * W)

        _max_algo = max(int(s.key) for s in _REGISTRY)
        choice = input(f"Choose an option (0–{max(20, _max_algo)}): ").strip()

        if choice == "0":
            print("\nGoodbye! 🚀\n")
            break

        elif choice == "16":
            run_benchmark(my_maze, delay, skip_frames, terrain_active, dispatch_fn=_dispatch_algorithm)
            flush_stdin()
            input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

        elif choice == "17":
            show_tutorial()
            continue

        elif choice == "18":
            fog_mode = not fog_mode
            status   = f"{C_BACK}ENABLED{C_END}" if fog_mode else f"{C_DOT}DISABLED{C_END}"
            print(f"\n  🌫️  Fog of War {status}.")
            if fog_mode:
                print(
                    f"  {C_DIM}  Visual mode: hides unvisited cells during animation.\n"
                    f"  Algorithms still have full global maze knowledge — this\n"
                    f"  visualises the search frontier, not partial observability.{C_END}"
                )
            time.sleep(0.8)
            continue

        elif choice == "19":
            hypothesis_mode = not hypothesis_mode
            if hypothesis_mode:
                hyp_pts = hyp_max_pts = 0
                print(
                    f"\n  {C_HYP}🔮 Hypothesis Challenge ENABLED.{C_END}\n"
                    "  Before each algorithm run you will be asked to predict\n"
                    "  its behaviour. Your predictions are scored after each run."
                )
            else:
                print(
                    f"\n  {C_DOT}🔮 Hypothesis Challenge DISABLED.{C_END}"
                    f"  Final score: {hyp_pts}/{hyp_max_pts} pts"
                )
            time.sleep(1.2)
            continue

        elif choice == "20":
            run_race(
                my_maze, delay, skip_frames, terrain_active, fog_mode,
                dispatch_fn=_dispatch_algorithm,
                start_recording=_start_recording,
                stop_recording=_stop_recording,
            )
            continue

        elif choice in _ALGO_NAMES:
            m_copy:      list[list[int | str]]      = [row[:] for row in my_maze]
            visit_count: dict[tuple[int, int], int] = {}
            fog: set[tuple[int, int]] | None        = (
                {(0, 0), (rows - 1, cols - 1)} if fog_mode else None
            )

            predictions: dict[str, bool | int] = {}
            if hypothesis_mode:
                predictions = _hypothesis_pre_run(_ALGO_NAMES[choice])
                hyp_max_pts += 4

            _set_active_complexity(_ALGO_NAMES[choice])

            _start_recording()
            try:
                result = _dispatch_algorithm(
                    choice, m_copy, delay, skip_frames, fog, visit_count
                )
            finally:
                recording = _stop_recording()
                _clear_active_complexity()


            show_report_card(_ALGO_NAMES[choice], result, terrain_active)

            if hypothesis_mode and predictions:
                pts      = _hypothesis_post_run(predictions, result, _ALGO_NAMES[choice])
                hyp_pts += pts

                _W_REV = 58
                clear_screen()
                print(f"\n{'═' * _W_REV}")
                print(_center_ansi(
                    f"{C_HYP}🔮  HYPOTHESIS RESULTS — {_ALGO_NAMES[choice]}{C_END}",
                    _W_REV,
                ))
                print(f"{'═' * _W_REV}")
                pts_label = f"+{pts} pt{'s' if pts != 1 else ''}"
                print(f"\n  {C_HYP}Round Score   :  {pts_label}{C_END}")
                print(f"  {C_HYP}Session Total :  {hyp_pts} / {hyp_max_pts} pts{C_END}")
                if hyp_max_pts > 0:
                    _pct    = hyp_pts / hyp_max_pts * 100
                    _filled = int(_pct / 5)
                    _bar    = f"{'█' * _filled}{'░' * (20 - _filled)}"
                    print(f"  {C_HYP}[{_bar}]  {_pct:.0f}%{C_END}")
                print(f"\n{'─' * _W_REV}")
                input(f"  {C_HYP}📋 Press ENTER to explore post-run tools…{C_END} ")

            has_heatmap = bool(visit_count)
            has_autopsy = bool(recording)
            has_duel    = result.steps != float('inf')
            if not has_duel:
                print(
                    f"  {C_DIM}(Duel unavailable — requires a successful run "
                    f"with a valid solution path){C_END}"
                )

            opts: list[str] = []
            if has_heatmap:
                opts.append("[h]eatmap")
            if has_autopsy:
                opts.append("[a]utopsy")
            if has_duel:
                opts.append("[d]uel")

            if opts:
                prompt_opts = "  ".join(opts) + "  ENTER=done"
                while True:
                    post_choice = input(
                        f"\n  ✨ Post-run: {prompt_opts}: "
                    ).strip().lower()

                    if post_choice == '':
                        break

                    if post_choice in {'h', 'heatmap'} and has_heatmap:
                        render_heatmap(visit_count, m_copy, _ALGO_NAMES[choice])
                        input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

                    elif post_choice in {'a', 'autopsy'} and has_autopsy:
                        run_autopsy(my_maze, recording, _ALGO_NAMES[choice])

                    elif post_choice in {'d', 'duel'} and has_duel:
                        run_duel(my_maze, m_copy, result, _ALGO_NAMES[choice], terrain_active, dispatch_fn=_dispatch_algorithm)
                        input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

                    else:
                        print(f"  (Unrecognised — try: {prompt_opts})")
            else:
                input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

        else:
            print("  Invalid option — please try again.")
            continue

        # After post-run tools: ask whether to keep or regenerate the maze
        while True:
            ans = input("\n  [ENTER/n] keep this maze   [y] generate new maze: ").strip().lower()
            if ans in {'y', 'yes'}:
                my_maze, delay, skip_frames, terrain_active = setup_new_maze()
                recording       = []
                m_copy          = []
                visit_count     = {}
                fog             = None
                if hypothesis_mode and hyp_max_pts > 0:
                    print(
                        f"  {C_DIM}🔮 Hypothesis score carries over: "
                        f"{hyp_pts}/{hyp_max_pts} pts  "
                        f"(toggle off/on to reset){C_END}"
                    )
                break
            elif ans in {'n', 'no', ''}:
                break
            else:
                print("  Please answer y or n.")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        import sys
        sys.stderr.close()
        sys.exit(0)
