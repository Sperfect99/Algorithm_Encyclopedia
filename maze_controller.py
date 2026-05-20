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
    _check_terminal_size, _term_width, _term_height, flush_stdin,
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
    run_multi_stats,
    save_maze,
    load_maze,
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

    tw = _term_width()
    th = _term_height()

    # Which levels actually fit right now — a maze needs at least maze_cols
    # terminal columns and maze_rows+5 rows (legend + HUD + breathing room).
    max_level = max(
        (lvl for lvl, (r, c) in MAZE_SIZES.items()
         if c <= tw and r + 5 <= th),
        default=0,
    )

    print("Select Maze Complexity Level:\n")
    for lvl, (r, c) in MAZE_SIZES.items():
        label     = _SIZE_LABELS[lvl]
        race_note = ""
        if c * 2 + 7 > 120:
            race_note = f"  {C_RACE}(Race Mode needs ≥{c*2+7} cols){C_END}"
        if lvl > max_level:
            print(f"  {C_DIM}{lvl:>2}  →  {r:>2} × {c:<3} grid  (needs {c}×{r+5} terminal){C_END}")
        else:
            print(f"  {lvl:>2}  →  {r:>2} × {c:<3} grid  ({label}){race_note}")

    if max_level < 10:
        print(
            f"\n  {C_BACK}⚠  Levels {max_level + 1}–10 need a larger terminal."
            f"  Resize to unlock them.{C_END}"
        )

    print()
    while True:
        raw = input(f"Enter level (0-{max_level}) or [L] load a saved maze: ").strip()
        if raw.lower() in {'l', 'load'}:
            loaded = load_maze()
            if loaded:
                maze, terrain_active = loaded
                l_rows, l_cols = len(maze), len(maze[0])
                if l_cols > tw or l_rows + 5 > th:
                    print(
                        f"\n  {C_BACK}⚠  This maze ({l_rows}×{l_cols}) may be wider"
                        f" than your terminal ({tw}×{th}).{C_END}"
                        f"\n  Resize before running if it looks off."
                    )
                delay, skip_frames = _prompt_speed()
                return maze, delay, skip_frames, terrain_active
            continue
        try:
            comp = int(raw)
            if 0 <= comp <= max_level:
                break
            elif 0 <= comp <= 10:
                print(
                    f"  Level {comp} needs a {MAZE_SIZES[comp][1]}×"
                    f"{MAZE_SIZES[comp][0]+5} terminal."
                    f"  Max available now: {max_level}."
                )
            else:
                print(f"  Please enter 0–{max_level} or L.")
        except ValueError:
            print(f"  Invalid — enter a number (0–{max_level}) or L to load a file.")

    maze_rows, maze_cols = MAZE_SIZES[comp]

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



# --- CUSTOM PLUGIN SYSTEM ---

_CUSTOM_STEP_CAP: int = 200_000   # stops infinite loops in custom algos


def _discover_plugins() -> dict[str, dict]:
    """Scan custom/ for .py files that expose a solve() function.

    Creates the folder if it doesn't exist so first-time users don't
    get a confusing FileNotFoundError. Returns a dict mapping letter keys
    ('a', 'b', ...) to plugin info dicts.
    """
    import importlib.util

    custom_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom")
    os.makedirs(custom_dir, exist_ok=True)

    plugins: dict[str, dict] = {}
    letters = "abcdefghijklmnopqrstuvwxyz"
    idx     = 0

    for fname in sorted(os.listdir(custom_dir)):
        if fname.startswith("_") or not fname.endswith(".py"):
            continue
        if idx >= len(letters):
            print(f"  ⚠️  custom/: more than 26 plugins — only first 26 loaded")
            break

        path = os.path.join(custom_dir, fname)
        try:
            spec_mod = importlib.util.spec_from_file_location(
                f"custom.{fname[:-3]}", path
            )
            mod = importlib.util.module_from_spec(spec_mod)
            spec_mod.loader.exec_module(mod)

            if not hasattr(mod, "solve") or not callable(mod.solve):
                print(f"  ⚠️  custom/{fname}: no solve() — skipped")
                continue

            info  = getattr(mod, "PLUGIN_INFO", {})
            name  = info.get("name", fname[:-3].replace("_", " ").title())
            note  = info.get("note", "custom algorithm")
            key   = letters[idx]

            plugins[key] = {"name": name, "note": note, "solve": mod.solve, "file": fname}
            idx += 1

        except Exception as exc:
            print(f"  ⚠️  custom/{fname}: failed to load ({exc}) — skipped")

    return plugins


def _make_plugin_spec(key: str, name: str, note: str) -> AlgorithmSpec:
    """Build a minimal AlgorithmSpec for a custom plugin.

    Custom plugins don't have all the metadata that built-in algorithms do,
    so this fills in sensible defaults for the fields the UI actually reads.
    """
    return AlgorithmSpec(
        key=key, module_name="", display_name=name,
        bench_name=name[:12], section="Custom",
        menu_note=note,
        big_o="T:?  S:?  ▸ custom algorithm",
        verdict="Custom algorithm — no built-in verdict.",
        tutorial_title=name, tutorial_body="Custom algorithm.",
    )


def _capped_solve(solve_fn, maze, fog, visit_count):
    """Wrap a custom solve() with a step limit.

    If a plugin never yields a 'done' event the program would hang forever.
    This catches that at 200k steps — way above any built-in algorithm on
    any maze — and surfaces it as a failure with a clear message.
    """
    steps = 0
    for state in solve_fn(maze, fog=fog, visit_count=visit_count):
        yield state
        if state.get("type") == "step":
            steps += 1
            if steps >= _CUSTOM_STEP_CAP:
                yield {
                    "type":    "done",
                    "result":  RunResult(float("inf"), 0.0, 0, 0),
                    "message": (
                        f"⚠️  Plugin hit the {_CUSTOM_STEP_CAP:,}-step cap. "
                        f"Check solve() for an infinite loop."
                    ),
                }
                return
        if state.get("type") == "done":
            return
# kicks in — all 20 options stay visible, just without section headers.
_FULL_MENU_H: int = 41


def _compact_menu(
    W:              int,
    rows:           int,
    cols:           int,
    speed_lbl:      str,
    terrain_lbl:    str,
    fog_lbl:        str,
    hyp_lbl:        str,
    terrain_active: bool,
    fog_mode:       bool,
    hypothesis_mode: bool,
    plugins:        dict | None = None,
) -> None:
    """2-column algorithm grid for short terminals.

    All 20 options fit in ~18 lines. Nothing hidden, nothing paginated.
    ★ = cost or hop optimal   [PQ✦] = priority queue inspector active
    """
    def _pad(text: str, width: int) -> str:
        # Pad ANSI-aware — measures visual width, not raw string length
        return text + " " * max(0, width - _visual_width(_strip_ansi(text)))

    specs = list(_REGISTRY)
    col1  = specs[:8]    # algorithms 1–8
    col2  = specs[8:]    # algorithms 9–15

    print("\n" + "═" * W)
    print(_center_ansi("🎓  MAZE SOLVER — THE PROFESSOR'S EDITION  V7  🎓", W))
    print("═" * W)
    print(
        f"  Maze: {C_BIGO}{rows}×{cols}{C_END}"
        f"  |  Speed: {C_DOT}{speed_lbl}{C_END}"
        f"  |  Terrain: {terrain_lbl}"
        f"  |  Fog: {fog_lbl}"
    )
    print("─" * W)

    for i, s1 in enumerate(col1):
        star1 = "★" if (s1.cost_optimal or s1.hop_optimal) else " "
        pq1   = " [PQ✦]" if s1.pq_inspector else ""
        name1 = s1.display_name[:17]
        left  = f"  {s1.key:>2}. {C_START}{name1:<17}{C_END} {star1}{pq1}"

        if i < len(col2):
            s2    = col2[i]
            star2 = "★" if (s2.cost_optimal or s2.hop_optimal) else " "
            pq2   = " [PQ✦]" if s2.pq_inspector else ""
            name2 = s2.display_name[:17]
            right = f"  {s2.key:>2}. {C_START}{name2:<17}{C_END} {star2}{pq2}"
        else:
            right = f"  {C_DIM}[h]heatmap  [a]utopsy  [d]uel  ENTER=done{C_END}"

        print(_pad(left, 46) + right)

    print("─" * W)

    t_on = terrain_active
    print(
        f"  16.🏆Benchmark  17.📚Tutorial"
        f"  18.Fog:{fog_lbl}  19.Hyp:{hyp_lbl}"
        f"  20.{C_RACE}🏎 Race{C_END}  21.📊Stats"
    )
    print(
        f"     🌿 Terrain: {terrain_lbl}"
        f"   {C_BIGO}▲ Big-O HUD{C_END} always on"
        f"   {C_PQ}🗂 PQ: A* / Dijkstra / Greedy{C_END}"
    )
    print("─" * W)
    print("  0. Exit")
    if plugins:
        keys_line = "  ".join(f"[{k}] {p['name']}" for k, p in plugins.items())
        print(f"  {C_PATH}Custom:{C_END} {keys_line}")


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

    # Load custom plugins once per session. _discover_plugins() also creates
    # the custom/ folder if it's missing so it's there for next time.
    _plugins = _discover_plugins()
    if _plugins:
        print(
            f"\n  {C_PATH}Loaded {len(_plugins)} custom plugin(s):"
            f" {', '.join(p['name'] for p in _plugins.values())}{C_END}"
        )
        time.sleep(0.8)

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

        W  = _term_width()
        TH = _term_height()

        # Soft warning — shown as one line in the menu header if the terminal
        # is on the small side. Re-checked every iteration so a resize is
        # picked up automatically on the next keypress.
        _size_warn = (
            f"  {C_BACK}⚠  Small terminal ({W}×{TH}) — resize for larger mazes{C_END}"
            if W < 80 or TH < 30 else ""
        )

        if TH >= _FULL_MENU_H:
            # Full layout — section headers, descriptions, everything
            print("\n" + "═" * W)
            print(_center_ansi("🎓  MAZE SOLVER — THE PROFESSOR'S EDITION  V7  🎓", W))
            print("═" * W)
            if _size_warn:
                print(_size_warn)
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
            print("  21. 📊  Multi-Run Stats (N runs across fresh mazes)")
            print(f"      🌿 Terrain        — {terrain_lbl}  (set at generation)")
            print(f"  {C_BIGO}  📐 Big-O HUD  — always active during algorithm runs{C_END}")
            print(f"  {C_PQ}  🗂  PQ Inspector — active for A*, Dijkstra, Greedy [PQ✦]{C_END}")
            print("  0.  Exit")
            if _plugins:
                print("  ─── Custom Algorithms ───────────────────────────────────")
                for key, p in _plugins.items():
                    print(f"  {key}.  {p['name']:<20} ({p['note']})")
            print("─" * W)
        else:
            # Compact 2-column layout — all 20 options, ~18 lines total
            _compact_menu(
                W, rows, cols,
                speed_lbl, terrain_lbl, fog_lbl, hyp_lbl,
                terrain_active, fog_mode, hypothesis_mode,
                _plugins,
            )

        _max_algo  = max(int(s.key) for s in _REGISTRY)
        _plug_hint = f" or {'/'.join(_plugins)}" if _plugins else ""
        choice     = input(f"Choose an option (0–{max(21, _max_algo)}{_plug_hint}): ").strip()

        if choice == "0":
            print("\nGoodbye! 🚀\n")
            break

        elif choice == "16":
            run_benchmark(my_maze, delay, skip_frames, terrain_active, dispatch_fn=_dispatch_algorithm)
            flush_stdin()

        elif choice == "17":
            show_tutorial()
            continue

        elif choice == "21":
            run_multi_stats(dispatch_fn=_dispatch_algorithm)
            flush_stdin()
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

        elif choice.lower() in _plugins:
            plugin  = _plugins[choice.lower()]
            spec    = _make_plugin_spec(choice.lower(), plugin["name"], plugin["note"])
            maze_copy    = [row[:] for row in my_maze]
            visit_count  = {} if True else {}
            fog          = set(fog if fog_mode and fog else [])
            result = run_algorithm(
                lambda m, fog=None, visit_count=None: _capped_solve(
                    plugin["solve"], m, fog, visit_count
                ),
                maze_copy, spec, delay, skip_frames,
                fog if fog_mode else None,
                visit_count,
            )
            # post-run options (heatmap, autopsy, duel) same as built-in algos
            m_copy      = maze_copy
            last_result = result

        else:
            print("  Invalid option — please try again.")
            continue

        # After post-run tools: ask whether to keep, save, or regenerate the maze
        while True:
            ans = input("\n  [ENTER/n] keep   [y] new maze   [s] save maze: ").strip().lower()
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
            elif ans in {'s', 'save'}:
                path = save_maze(my_maze, terrain_active)
                if path:
                    print(f"  ✅ Saved to {C_PATH}{path}{C_END}")
                time.sleep(0.8)
            elif ans in {'n', 'no', ''}:
                break
            else:
                print("  Please answer y, n, or s.")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        import sys
        sys.stderr.close()
        sys.exit(0)