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

from maze_genV4 import (
    generate_maze, add_terrain, MAZE_SIZES, _GEN_CYCLE,
    maze_difficulty, maze_analyse, MazeStats,
)

from core.types        import RunResult, _StepRecord
from core.grid         import terrain_cost, DIRECTIONS, PASSABLE
from core.graph        import manhattan_distance, validate_path
from ui.theme          import *                           # noqa: F401,F403
from ui.terminal_utils import (
    clear_screen, _strip_ansi, _visual_width, _center_ansi,
    _check_terminal_size, _term_width, _term_height, flush_stdin,
    restore_terminal,
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
    show_topology_panel,
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
    export_maze_ascii,
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
_ACTIVE_DIFF_SLOT:       list[int] = [-1]


def _set_active_complexity(algo_name: str) -> None:
    _ACTIVE_COMPLEXITY_SLOT[0] = _ALGO_BIG_O.get(algo_name, "")


def _clear_active_complexity() -> None:
    _ACTIVE_COMPLEXITY_SLOT[0] = ""


def _set_active_diff(diff: int) -> None:
    _ACTIVE_DIFF_SLOT[0] = diff


def _clear_active_diff() -> None:
    _ACTIVE_DIFF_SLOT[0] = -1


# --- HEURISTIC STATE ---

# Import presets list from astar so we don't duplicate the definitions.
# Loaded lazily on first access to avoid a circular import at startup.
def _get_heuristic_presets() -> list[tuple[str, bool, object]]:
    """Load the preset list from astar.py. Falls back to manhattan-only
    if the import fails so the session can still start normally.
    """
    try:
        from algorithms.pathfinding.astar import HEURISTIC_PRESETS
        return HEURISTIC_PRESETS
    except ImportError:
        import math
        return [("Manhattan |Δr|+|Δc|", True,
                 lambda r,c,gr,gc,m: abs(gr-r)+abs(gc-c))]


def _discover_heuristic_plugins() -> dict[str, tuple[str, object]]:
    """Scan custom/heuristics/ for .py files that expose heuristic().

    Returns {letter_key: (display_name, callable)} — keys start at 'a'.
    Files whose names start with '_' are skipped (template, __init__, etc.).
    A plugin that fails to import is logged and skipped.
    """
    import os, importlib.util

    plugin_dir = os.path.join(os.path.dirname(__file__), "custom", "heuristics")
    try:
        os.makedirs(plugin_dir, exist_ok=True)
    except OSError:
        return {}

    plugins: dict[str, tuple[str, object]] = {}
    _reserved = {'n', 't', 'x', 'h', 'g'}  # skip keys already bound in the main menu
    letters  = iter(k for k in "abcdefghijklmnopqrstuvwxyz" if k not in _reserved)

    try:
        entries = sorted(f for f in os.listdir(plugin_dir)
                         if f.endswith(".py") and not f.startswith("_"))
    except OSError:
        return plugins

    for fname in entries:
        key  = next(letters, None)
        if key is None:
            break
        name = fname[:-3]
        path = os.path.join(plugin_dir, fname)
        try:
            spec   = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(module)                  # type: ignore[union-attr]
            fn = getattr(module, "heuristic", None)
            if callable(fn):
                # Quick smoke-test — wrong signature or a divide-by-zero
                # in the formula surfaces here, not mid-run.
                try:
                    result = fn(0, 0, 1, 1, [[0]])
                    if not isinstance(result, (int, float)):
                        raise TypeError(
                            f"heuristic() must return a number, got {type(result).__name__}"
                        )
                    plugins[key] = (name, fn)
                except Exception as exc:
                    print(f"  ⚠️  Plugin {fname} rejected: {exc}")
        except Exception as exc:
            print(f"  ⚠️  Heuristic plugin {fname} failed to load: {exc}")

    return plugins



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
    choice:       str,
    maze:         list[list[int | str]],
    delay:        float,
    skip_frames:  int,
    fog:          set[tuple[int, int]] | None,
    visit_count:  dict[tuple[int, int], int] | None,
    heuristic_fn: object | None = None,
    beam_width:   int           = 3,
) -> RunResult:
    """Route a menu choice string to the matching generator and run it.

    Also handles the large-maze warning for slow algorithms (driven by the
    AlgorithmSpec so we don't need any hardcoded algorithm names here).
    heuristic_fn is only forwarded when the selected algorithm is A*.
    beam_width is only forwarded when the selected algorithm is Beam Search.
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

    # A* is the only algorithm with a swappable heuristic. Pass it through
    # as a keyword arg when provided; other algorithms ignore unknown kwargs
    # since they use positional-only or **kwargs signatures.
    if spec.module_name == "astar" and heuristic_fn is not None:
        gen = factory(maze, fog=fog, visit_count=vc, heuristic_fn=heuristic_fn)
    elif spec.module_name == "beam_search":
        gen = factory(maze, fog=fog, visit_count=vc, beam_width=beam_width)
    else:
        gen = factory(maze, fog=fog, visit_count=vc)  # type: ignore[operator]

    return run_algorithm(
        gen, maze, skip_frames, delay, algo_name,
        _ACTIVE_COMPLEXITY_SLOT, _ACTIVE_RECORDING,
        fog=fog,
        maze_diff=_ACTIVE_DIFF_SLOT[0],
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


def setup_new_maze(
    generator_type: str = "dfs",
) -> tuple[list[list[int | str]], float, int, bool, str]:
    """Prompt for generator/complexity/speed/terrain and return a freshly generated maze.

    Returns (maze, delay, skip_frames, terrain_active, generator_type).
    When the user chooses [L] to load a saved maze, generator_type is
    set to the original generator name from the file — callers can detect
    a load by checking whether _current_seed was meaningful, but a simpler
    signal is the _LOADED_MAZE sentinel returned in generator_type when
    the maze came from a file (see below).
    """
    from maze_genV4 import GENERATORS, _GEN_CYCLE

    clear_screen()
    _SIZE_LABELS = {
        0: "tiny",   1: "tiny",   2: "small",  3:  "small",
        4: "medium", 5: "medium", 6: "large",  7:  "large",
        8: "huge",   9: "huge",  10: "massive",
    }

    # --- generator selection ---
    print("Select Maze Generator:\n")
    for i, key in enumerate(_GEN_CYCLE, 1):
        default = "  (default)" if key == generator_type else ""
        print(f"  {i})  {GENERATORS[key]}{default}")
    print()
    while True:
        raw = input(f"  Choice (1-{len(_GEN_CYCLE)}) or ENTER to keep [{generator_type.upper()}]: ").strip()
        if raw == "":
            break
        if raw.isdigit() and 1 <= int(raw) <= len(_GEN_CYCLE):
            generator_type = _GEN_CYCLE[int(raw) - 1]
            break
        print(f"  Enter 1–{len(_GEN_CYCLE)} or ENTER.")

    tw = _term_width()
    th = _term_height()

    # Levels that fit without any clipping.  The +2 accounts for the two-space
    # left margin the renderer prints on every row.  Levels above this threshold
    # still work — they get a warning, not a hard block.
    def _fits(r: int, c: int) -> bool:
        return c + 2 <= tw and r + 5 <= th

    max_fits = max(
        (lvl for lvl, (r, c) in MAZE_SIZES.items() if _fits(r, c)),
        default=0,
    )

    print(f"\nSelect Maze Complexity Level:  [{generator_type.upper()}]\n")
    for lvl, (r, c) in MAZE_SIZES.items():
        label     = _SIZE_LABELS[lvl]
        race_note = ""
        if c * 2 + 7 > 120:
            race_note = f"  {C_RACE}(Race Mode needs ≥{c*2+7} cols){C_END}"
        if not _fits(r, c):
            print(
                f"  {C_DIM}{lvl:>2}  →  {r:>2} × {c:<3} grid  "
                f"(needs {c+2}×{r+5} terminal — yours is {tw}×{th}){C_END}"
            )
        else:
            print(f"  {lvl:>2}  →  {r:>2} × {c:<3} grid  ({label}){race_note}")

    if max_fits < 10:
        print(
            f"\n  {C_DIM}Levels {max_fits + 1}–10 shown above may clip on your current "
            f"terminal ({tw}×{th}).  You can still pick them — resize first "
            f"or ignore if you know your terminal is wide enough.{C_END}"
        )

    print()
    while True:
        raw = input("Enter level (0-10) or [L] load a saved maze: ").strip()
        if raw.lower() in {'l', 'load'}:
            loaded = load_maze()
            if loaded:
                maze, terrain_active, loaded_gen = loaded
                l_rows, l_cols = len(maze), len(maze[0])
                if not _fits(l_rows, l_cols):
                    print(
                        f"\n  {C_BACK}⚠  This maze ({l_rows}×{l_cols}) may clip"
                        f" on your terminal ({tw}×{th}).{C_END}"
                        f"\n  Resize before running if it looks off."
                    )
                delay, skip_frames = _prompt_speed()
                # Prefix the generator name so _setup_maze can tell this
                # was loaded rather than generated, and skip seed display.
                return maze, delay, skip_frames, terrain_active, f"loaded:{loaded_gen}"
            continue
        try:
            comp = int(raw)
            if 0 <= comp <= 10:
                r, c = MAZE_SIZES[comp]
                if not _fits(r, c):
                    print(
                        f"\n  {C_BACK}⚠  Level {comp} ({r}×{c}) needs a "
                        f"{c+2}×{r+5} terminal — yours is {tw}×{th}."
                        f"  It may clip, but you can run it anyway.{C_END}"
                    )
                    confirm = input("  Continue? (y/n): ").strip().lower()
                    if confirm not in {'y', 'yes', ''}:
                        continue
                break
            else:
                print("  Please enter 0–10 or L.")
        except ValueError:
            print("  Invalid — enter a number (0–10) or L to load a file.")

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
    maze = generate_maze(comp, generator_type)
    if terrain_active:
        add_terrain(maze)

    return maze, delay, skip_frames, terrain_active, generator_type



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
    _reserved = {'n', 't', 'x', 'h', 'g'}  # skip keys already bound in the main menu
    letters   = [k for k in "abcdefghijklmnopqrstuvwxyz" if k not in _reserved]
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
    gen_lbl:        str = "",
    size_lbl:       str = "",
    diff_lbl:       str = "",
    h_lbl:          str = "",
    beam_lbl:       str = "",
    no_maze:        bool = False,
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
        f"  Maze: {size_lbl}"
        f"  |  Speed: {C_DOT}{speed_lbl}{C_END}"
        f"  |  Terrain: {terrain_lbl}"
        f"  |  Fog: {fog_lbl}"
        f"  |  Gen: {gen_lbl}"
        f"  |  Diff: {diff_lbl}"
    )
    if h_lbl:
        print(f"  {C_DIM}A* heuristic: {h_lbl}   │   Beam width: {beam_lbl}{C_END}")
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
    gen23 = (f"  {C_PATH}23.⚡GenMaze{C_END}" if no_maze
             else f"  27.⚡GenMaze")
    print(
        f"  20.🏆Benchmark  21.📚Tutorial"
        f"  22.Fog:{fog_lbl}  23.Hyp:{hyp_lbl}"
        f"  24.{C_RACE}🏎 Race{C_END}  25.📊Stats  26.🗺️Gen:{gen_lbl}"
        f"{gen23}"
        f"  {C_DIM}[n]New  [t]Topo  [x]Export{C_END}"
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

def main(mode: str = "full", seed: int | None = None) -> None:
    """Entry point. Wraps the session loop with clean Ctrl-C / EOF handling
    so the terminal doesn't get a noisy traceback when running in class."""
    try:
        _main_loop(mode=mode, seed=seed)
    except (KeyboardInterrupt, EOFError):
        restore_terminal()
    except Exception:
        restore_terminal()
        raise


def _main_loop(mode: str = "full", seed: int | None = None) -> None:
    """The actual interactive session. Extracted from main() so the exception
    handler in main() stays clean.

    mode='full'  — everything visible, default behaviour
    mode='learn' — algorithms 1-15 + Tutorial + Fog + Hypothesis only;
                   no Benchmark, Race, Multi-run, Generator, or plugins
    seed         — starting random seed; None means random per maze
    """
    import random as _random

    _learn = (mode == "learn")

    # Seed tracking — each maze gets a deterministic seed derived from the
    # base. If no --seed was given, each maze picks its own random seed so
    # the session is still reproducible one maze at a time (seed shown in HUD).
    _base_seed:   int | None = seed
    _maze_count:  int        = 0
    _current_seed: int       = (
        seed if seed is not None else _random.randint(1, 999_999)
    )

    def _next_seed() -> int:
        """Return the seed for the next maze and advance the counter."""
        nonlocal _maze_count, _current_seed
        if _base_seed is not None:
            s = _base_seed + _maze_count
        else:
            s = _random.randint(1, 999_999)
        _maze_count  += 1
        _current_seed = s
        return s

    generator_type: str = "dfs"

    # No maze at startup — generated the first time an algorithm is chosen.
    # These defaults are used until setup_new_maze() is called.
    my_maze:        list | None    = None
    _stats:         MazeStats | None = None
    _diff:          int            = -1
    delay:          float          = 0.05
    skip_frames:    int            = 1
    terrain_active: bool           = False

    def _setup_maze() -> None:
        """Run setup, seed the RNG, compute stats, show topology panel."""
        nonlocal my_maze, _stats, _diff, delay, skip_frames, terrain_active
        nonlocal generator_type, _current_seed
        s = _next_seed()
        _random.seed(s)
        my_maze, delay, skip_frames, terrain_active, generator_type = setup_new_maze(generator_type)
        # When the user loads a saved maze the returned generator_type is
        # prefixed with "loaded:" — strip it and mark the seed as N/A.
        if generator_type.startswith("loaded:"):
            generator_type = generator_type[len("loaded:"):]
            _current_seed  = -1   # sentinel: seed is meaningless for loaded mazes
        _stats = maze_analyse(my_maze)
        _diff  = _stats.difficulty
        show_topology_panel(_stats, generator_type, len(my_maze), len(my_maze[0]))

    # Load custom plugins once at session start
    _plugins = _discover_plugins()
    if _plugins:
        print(
            f"\n  {C_PATH}Loaded {len(_plugins)} custom plugin(s):"
            f" {', '.join(p['name'] for p in _plugins.values())}{C_END}"
        )
        time.sleep(0.8)

    # Heuristic state — presets from astar.py, plugins from custom/heuristics/
    # Index 0 = Manhattan (default). Rebuilt on each session start so new
    # plugin files are picked up without restarting the whole program.
    _heuristic_presets  = _get_heuristic_presets()   # list of (label, admissible, fn)
    _heuristic_plugins  = _discover_heuristic_plugins()
    _active_h_idx: int  = 0                           # index into presets; -1 = plugin
    _active_h_key: str  = ""                          # plugin letter key when idx == -1
    _active_h_fn        = _heuristic_presets[0][2]    # callable — starts as manhattan
    _active_beam_width  = 3                            # int — default width for Beam Search
    _active_h_label     = _heuristic_presets[0][0].split()[0]  # short name for info bar

    fog_mode:        bool                         = False
    hypothesis_mode: bool                         = False
    hyp_pts:         int                          = 0
    hyp_max_pts:     int                          = 0
    recording:       list[_StepRecord]            = []

    while True:
        if my_maze is not None:
            rows, cols = len(my_maze), len(my_maze[0])
            size_lbl   = f"{C_BIGO}{rows}×{cols}{C_END}"
        else:
            rows, cols = 0, 0
            size_lbl   = f"{C_DIM}none — pick an algorithm to generate{C_END}"

        fog_lbl     = f"{C_BACK}ON {C_END}" if fog_mode      else f"{C_DOT}OFF{C_END}"
        terrain_lbl = f"{C_MUD}ON {C_END}"  if terrain_active else f"{C_DOT}OFF{C_END}"
        gen_lbl     = f"{C_PATH}{generator_type.upper()}{C_END}"
        _dc         = C_PATH if _diff <= 25 else C_START if _diff <= 50 else C_RACE if _diff <= 75 else C_BACK
        diff_lbl    = f"{_dc}{_diff:>3}{C_END}" if _diff >= 0 else f"{C_DIM} — {C_END}"
        seed_lbl    = (
            f"{C_DIM}loaded{C_END}"    if _current_seed == -1 else
            f"{C_DIM}{_current_seed}{C_END}" if my_maze is not None else
            f"{C_DIM} — {C_END}"
        )
        if _active_h_idx < 0:
            _adm = "?"   # plugin — admissibility unknown until proven
        elif _heuristic_presets[_active_h_idx][1]:
            _adm = "✓"
        else:
            _adm = "✗"
        h_lbl       = f"{C_BIGO}{_active_h_label}{C_END} {C_DIM}{_adm}{C_END}"
        beam_lbl    = f"{C_BIGO}w={_active_beam_width}{C_END}"
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

        if _learn:
            # Learn mode: algorithms + Tutorial + Fog + Hypothesis only.
            # Everything else is hidden so new users aren't overwhelmed.
            print("\n" + "═" * W)
            print(_center_ansi("🎓  MAZE SOLVER — LEARN MODE  📚", W))
            print("═" * W)
            print(
                f"  Maze: {size_lbl}"
                f"  |  Terrain: {terrain_lbl}"
                f"  |  Fog: {fog_lbl}"
                f"  |  Diff: {diff_lbl}"
            )
            print(
                f"  {C_DIM}Full experience: run without --learn"
                f"   |   [t] topology   [n] new maze{C_END}"
            )
            print()
            for _section_name, _specs in _MENU_SECTIONS.items():
                _bar = "─" * max(0, 49 - len(_section_name))
                print(f"  ─── {_section_name} {_bar}")
                for _sp in _specs:
                    print(f"  {_sp.key:>2}. {_sp.display_name:<20} ({_sp.menu_note})")
            print("  ─── V5 Post-Run Modes ───────────────────────────────────")
            print("  (After each run: [h]eatmap  [a]utopsy  [d]uel  ENTER=done)")
            print("  ─── Learning ────────────────────────────────────────────")
            print("  21. 📚  Tutorial        (data structures & complexity)")
            print(f"  22. 🌫️  Fog of War     — {fog_lbl}")
            print(f"  23. 🔮  Hypothesis     — {hyp_lbl}")
            print("  0.  Exit")
            print("─" * W)

        elif TH >= _FULL_MENU_H:
            # Full layout — section headers, descriptions, everything
            print("\n" + "═" * W)
            print(_center_ansi("🎓  MAZE SOLVER — THE PROFESSOR'S EDITION  V7  🎓", W))
            print("═" * W)
            if _size_warn:
                print(_size_warn)
            print(
                f"  Maze: {size_lbl}"
                f"  |  Speed: {C_DOT}{speed_lbl}{C_END}"
                f"  |  Terrain: {terrain_lbl}"
                f"  |  Fog: {fog_lbl}"
                f"  |  Gen: {gen_lbl}"
                f"  |  Diff: {diff_lbl}"
                f"  |  Seed: {seed_lbl}"
            )
            print(f"  {C_DIM}A* heuristic: {h_lbl}   [h] to change   │   Beam width: {beam_lbl}   [b] to change{C_END}")
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
            print("  20. 🏆  Run Benchmark   (all algorithms at once)")
            print("  21. 📚  Tutorial        (data structures & complexity)")
            print(f"  22. 🌫️  Fog of War     — {fog_lbl}")
            print(f"  23. 🔮  Hypothesis     — {hyp_lbl}")
            print(f"  24. {C_RACE}🏎️  Race Mode{C_END}      (two algorithms, split-screen)")
            print("  25. 📊  Multi-Run Stats (N runs across fresh mazes)")
            print(f"  26. 🗺️  Generator      — {gen_lbl}  [{' → '.join(k.upper() for k in _GEN_CYCLE)}]")
            print(f"      🌿 Terrain        — {terrain_lbl}  (set at generation)")
            if my_maze is None:
                print(f"  {C_PATH}23. ⚡  Generate Maze{C_END}  "
                      f"{C_BACK}← no maze yet — start here before Race or Benchmark{C_END}")
            else:
                print(f"  27. ⚡  Generate Maze  "
                      f"{C_DIM}(replaces current maze){C_END}")
            print(f"  {C_DIM}[n] New maze   [t] Topology   [x] Export ASCII{C_END}")
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
                gen_lbl,
                size_lbl,
                diff_lbl,
                h_lbl,
                beam_lbl,
                no_maze=my_maze is None,
            )

        _max_algo  = max(int(s.key) for s in _REGISTRY)
        _plug_hint = f" or {'/'.join(_plugins)}" if _plugins and not _learn else ""
        _no_maze   = my_maze is None
        _top       = max(27, _max_algo)
        choice     = input(
            f"Choose an option (0–{_top if not _learn else '19'}{_plug_hint}"
            f"{', n=new maze' if not _no_maze else ''}): "
        ).strip()

        # In learn mode silently redirect any hidden advanced option so
        # the user gets a helpful message rather than "invalid option".
        if _learn and choice in {"20", "24", "25", "26"}:
            print(
                f"  {C_DIM}That option is not available in learn mode."
                f"  Run without --learn for the full experience.{C_END}"
            )
            time.sleep(1.2)
            continue

        if choice == "0":
            print("\nGoodbye! 🚀\n")
            break

        # [n] — generate a new maze from scratch
        elif choice.lower() == "n":
            _setup_maze()
            continue

        # [h] — pick A* heuristic (preset or user plugin)
        elif choice.lower() == "h":
            clear_screen()
            W = _term_width()
            print("\n" + "═" * W)
            print(_center_ansi("🔢  A* HEURISTIC SELECTOR", W))
            print("═" * W)
            print(
                f"\n  {C_DIM}Admissible (✓): h never overestimates — A* returns the optimal path."
                f"\n  Inadmissible (✗): may return a suboptimal path but usually fewer steps."
                f"\n  Only affects A*. IDA* and Greedy Best-First have their own fixed heuristics."
                f"\n  Benchmark and Race Mode always use Manhattan for consistent comparisons.{C_END}\n"
            )
            print("  ─── Built-in presets ────────────────────────────────────")
            for i, (label, admissible, _) in enumerate(_heuristic_presets, 1):
                marker = f"{C_PATH}✓{C_END}" if admissible else f"{C_BACK}✗{C_END}"
                active = f"  {C_BIGO}← active{C_END}" if i - 1 == _active_h_idx else ""
                print(f"  {i}.  {label}  {marker}{active}")

            if _heuristic_plugins:
                print("\n  ─── Your plugins (custom/heuristics/) ───────────────")
                for key, (name, _) in _heuristic_plugins.items():
                    active = f"  {C_BIGO}← active{C_END}" if (
                        _active_h_idx == -1 and _active_h_key == key
                    ) else ""
                    print(f"  {key}.  {name}{active}")
            else:
                print(f"\n  {C_DIM}No custom plugins found. Drop a .py file into"
                      f" custom/heuristics/ to add your own.{C_END}")

            print(f"\n  ENTER = keep current ({_active_h_label})")
            print("─" * W)
            flush_stdin()
            raw = input("  Choice: ").strip()

            if raw == "":
                pass  # keep current
            elif raw.isdigit() and 1 <= int(raw) <= len(_heuristic_presets):
                idx             = int(raw) - 1
                _active_h_idx   = idx
                _active_h_key   = ""
                _active_h_fn    = _heuristic_presets[idx][2]
                _active_h_label = _heuristic_presets[idx][0].split()[0]
                adm_str = "admissible ✓" if _heuristic_presets[idx][1] else "inadmissible ✗"
                print(f"\n  A* heuristic → {C_BIGO}{_active_h_label}{C_END}  ({adm_str})")
                time.sleep(0.8)
            elif raw.lower() in _heuristic_plugins:
                key             = raw.lower()
                name, fn        = _heuristic_plugins[key]
                _active_h_idx   = -1
                _active_h_key   = key
                _active_h_fn    = fn
                _active_h_label = name
                print(f"\n  A* heuristic → {C_BIGO}{name}{C_END}  (admissibility unknown — user-defined)")
                time.sleep(0.8)
            else:
                print("  Invalid choice — heuristic unchanged.")
                time.sleep(0.7)
            continue

        elif choice.lower() == "b":
            clear_screen()
            W = _term_width()
            print("\n" + "═" * W)
            print(_center_ansi("📡  BEAM SEARCH WIDTH", W))
            print("═" * W)
            print(
                f"\n  {C_DIM}Controls how many nodes survive each pruning step."
                f"\n  width=1: pure hill-climbing (fastest, most likely to fail)."
                f"\n  width=∞: equivalent to Greedy Best-First (never prunes)."
                f"\n  Only affects Beam Search. Other algorithms ignore this.{C_END}\n"
            )
            print(f"  Current width: {C_BIGO}{_active_beam_width}{C_END}\n")
            print("─" * W)
            flush_stdin()
            raw = input("  New width (1–50, ENTER to keep): ").strip()
            if raw == "":
                pass
            elif raw.isdigit() and 1 <= int(raw) <= 50:
                _active_beam_width = int(raw)
                print(f"\n  Beam width → {C_BIGO}{_active_beam_width}{C_END}")
                time.sleep(0.7)
            else:
                print("  Invalid — beam width unchanged.")
                time.sleep(0.7)
            continue

        # [g] — cycle maze generator DFS → Kruskal → Prim
        elif choice.lower() == "g":
            idx_g          = _GEN_CYCLE.index(generator_type)
            generator_type = _GEN_CYCLE[(idx_g + 1) % len(_GEN_CYCLE)]
            print(f"\n  🗺️  Generator → {C_PATH}{generator_type.upper()}{C_END}  (takes effect on next maze)")
            time.sleep(0.7)
            continue

        # [t] — show topology panel for the current maze again
        elif choice.lower() == "t":
            if my_maze is None:
                print(f"  {C_BACK}No maze yet — pick an algorithm first.{C_END}")
            else:
                show_topology_panel(_stats, generator_type, rows, cols)
            continue

        elif choice.lower() == "x":
            if my_maze is None:
                print(f"  {C_BACK}No maze yet — pick an algorithm first.{C_END}")
            else:
                path = export_maze_ascii(my_maze, generator_type, _diff, _stats)
                if path:
                    print(f"  ✅ Exported to {C_PATH}{path}{C_END}")
                time.sleep(0.8)
            continue

        elif choice == "20":
            if my_maze is None:
                print(f"  {C_BACK}No maze yet.{C_END} Pick option {C_PATH}27{C_END} to generate one first.")
                continue
            run_benchmark(my_maze, delay, skip_frames, terrain_active, generator=generator_type, maze_diff=_diff, stats=_stats, dispatch_fn=_dispatch_algorithm)
            flush_stdin()

        elif choice == "21":
            show_tutorial()
            continue

        elif choice == "26":
            _cur = generator_type if generator_type in _GEN_CYCLE else _GEN_CYCLE[0]
            generator_type = _GEN_CYCLE[(_GEN_CYCLE.index(_cur) + 1) % len(_GEN_CYCLE)]
            print(f"\n  🗺️  Generator → {C_PATH}{generator_type.upper()}{C_END} — takes effect on next maze.")
            time.sleep(0.7)
            continue

        elif choice == "25":
            if my_maze is None:
                print(f"  {C_BACK}No maze yet.{C_END} Pick option {C_PATH}27{C_END} to generate one first.")
                continue
            run_multi_stats(dispatch_fn=_dispatch_algorithm, generator=generator_type)
            flush_stdin()
            continue

        elif choice == "22":
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

        elif choice == "23":
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

        elif choice == "27":
            _setup_maze()
            continue

        elif choice == "24":
            if my_maze is None:
                print(f"  {C_BACK}No maze yet.{C_END} Pick option {C_PATH}27{C_END} to generate one first.")
                continue
            run_race(
                my_maze, delay, skip_frames, terrain_active, fog_mode,
                dispatch_fn=_dispatch_algorithm,
                start_recording=_start_recording,
                stop_recording=_stop_recording,
            )
            continue

        elif choice in _ALGO_NAMES:
            # First time picking an algorithm — need a maze
            if my_maze is None:
                _setup_maze()
                if my_maze is None:
                    continue   # setup was cancelled

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
            _set_active_diff(_diff)

            _start_recording()
            try:
                result = _dispatch_algorithm(
                    choice, m_copy, delay, skip_frames, fog, visit_count,
                    heuristic_fn=_active_h_fn,
                    beam_width=_active_beam_width,
                )
            finally:
                recording = _stop_recording()
                _clear_active_complexity()
                _clear_active_diff()


            show_report_card(_ALGO_NAMES[choice], result, terrain_active, maze_diff=_diff)

            # Sanity check — catches algorithm bugs where the reported path_len
            # doesn't match what was actually stamped on the maze.
            # m_copy is used here, not my_maze — the algorithm runs on the copy
            # so that my_maze stays clean for heatmap, duel, and the next run.
            if result.path_len > 0:
                _path_err = validate_path(m_copy, result.path_len, result.path_cost)
                if _path_err:
                    print(f"  {C_BACK}⚠  path validator: {_path_err}{C_END}")

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

            # Let the user know if the autopsy recording was cut short.
            # This happens when a run has more steps than _AUTOPSY_MAX_FRAMES
            # (50 000) — the replay will stop early without explanation otherwise.
            if has_autopsy and result.steps != float('inf') and result.steps > 50_000:
                print(
                    f"  {C_DIM}⚠  autopsy recording capped at 50 000 frames "
                    f"({result.steps:,.0f} total steps) — replay covers the "
                    f"first portion of the run only.{C_END}"
                )
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
                        # Ask whether to enable the step-by-step explainer.
                        # Only offered for algorithms that have real decision
                        # logic — random algorithms skip straight to autopsy.
                        _algo_key = _ALGO_NAMES[choice]
                        _no_logic = {'Random Mouse', 'Randomized DFS'}
                        if _algo_key not in _no_logic:
                            flush_stdin()
                            _exp_raw = input(
                                f"\n  Enable step-by-step explanations?"
                                f"  ({C_PATH}b{C_END}=beginner  {C_BIGO}a{C_END}=advanced  {C_DIM}ENTER=off{C_END}): "
                            ).strip().lower()
                            _explain = _exp_raw in {'b', 'a', 'beginner', 'advanced', 'y', 'yes'}
                            _level   = "advanced" if _exp_raw in {'a', 'advanced'} else "beginner"
                        else:
                            _explain = False
                            _level   = "beginner"
                        run_autopsy(my_maze, recording, _algo_key,
                                    explain=_explain, level=_level)

                    elif post_choice in {'d', 'duel'} and has_duel:
                        run_duel(my_maze, m_copy, result, _ALGO_NAMES[choice], terrain_active, dispatch_fn=_dispatch_algorithm)
                        input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

                    else:
                        print(f"  (Unrecognised — try: {prompt_opts})")
            else:
                input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

        elif choice.lower() in _plugins:
            if my_maze is None:
                _setup_maze()
                if my_maze is None:
                    continue

            plugin       = _plugins[choice.lower()]
            spec         = _make_plugin_spec(choice.lower(), plugin["name"], plugin["note"])
            maze_copy    = [row[:] for row in my_maze]
            visit_count  = {}
            plugin_fog   = {(0, 0), (rows - 1, cols - 1)} if fog_mode else None
            _set_active_complexity(spec.display_name)
            _start_recording()
            try:
                result = run_algorithm(
                    _capped_solve(plugin["solve"], maze_copy, plugin_fog, visit_count),
                    maze_copy, skip_frames, delay, spec.display_name,
                    _ACTIVE_COMPLEXITY_SLOT, _ACTIVE_RECORDING,
                    fog=plugin_fog,
                    maze_diff=_diff,
                )
            finally:
                recording = _stop_recording()
                _clear_active_complexity()
            m_copy      = maze_copy
            last_result = result

            show_report_card(spec.display_name, result, terrain_active, maze_diff=_diff)

            if result.path_len > 0:
                _path_err = validate_path(m_copy, result.path_len, result.path_cost)
                if _path_err:
                    print(f"  {C_BACK}⚠  path validator: {_path_err}{C_END}")

            has_heatmap = bool(visit_count)
            has_autopsy = bool(recording)

            if has_autopsy and result.steps != float('inf') and result.steps > 50_000:
                print(
                    f"  {C_DIM}⚠  autopsy recording capped at 50 000 frames "
                    f"({result.steps:,.0f} total steps) — replay covers the "
                    f"first portion of the run only.{C_END}"
                )

            opts: list[str] = []
            if has_heatmap:
                opts.append("[h]eatmap")
            if has_autopsy:
                opts.append("[a]utopsy")

            if opts:
                prompt_opts = "  ".join(opts) + "  ENTER=done"
                while True:
                    post_choice = input(
                        f"\n  ✨ Post-run: {prompt_opts}: "
                    ).strip().lower()

                    if post_choice == '':
                        break

                    if post_choice in {'h', 'heatmap'} and has_heatmap:
                        render_heatmap(visit_count, m_copy, spec.display_name)
                        input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

                    elif post_choice in {'a', 'autopsy'} and has_autopsy:
                        flush_stdin()
                        _exp_raw = input(
                            f"\n  Enable step-by-step explanations?"
                            f"  ({C_PATH}b{C_END}=beginner  {C_BIGO}a{C_END}=advanced  {C_DIM}ENTER=off{C_END}): "
                        ).strip().lower()
                        _explain = _exp_raw in {'b', 'a', 'beginner', 'advanced', 'y', 'yes'}
                        _level   = "advanced" if _exp_raw in {'a', 'advanced'} else "beginner"
                        run_autopsy(my_maze, recording, spec.display_name,
                                    explain=_explain, level=_level)

                    else:
                        print(f"  (Unrecognised — try: {prompt_opts})")
            else:
                input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

        else:
            print("  Invalid option — please try again.")
            continue

        # After post-run tools: ask whether to keep, save, or generate a new maze.
        # "new maze" now goes through _setup_maze() which shows topology.
        while True:
            ans = input("\n  [ENTER/n] keep   [y] new maze   [s] save maze: ").strip().lower()
            if ans in {'y', 'yes'}:
                _setup_maze()
                recording   = []
                m_copy      = []
                visit_count = {}
                fog         = None
                if hypothesis_mode and hyp_max_pts > 0:
                    print(
                        f"  {C_DIM}🔮 Hypothesis score carries over: "
                        f"{hyp_pts}/{hyp_max_pts} pts  "
                        f"(toggle off/on to reset){C_END}"
                    )
                break
            elif ans in {'s', 'save'}:
                path = save_maze(my_maze, terrain_active, generator_type)
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
    except Exception as _exc:
        restore_terminal()
        print(f"\n  \u2716  Crashed: {type(_exc).__name__}: {_exc}")
        print("  Run through _encyclopedia_launcher.py for a fuller error report.")
        raise