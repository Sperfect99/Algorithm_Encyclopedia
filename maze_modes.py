"""
maze_modes.py — interactive post-run and system modes.

The four modes extracted from the old monolith:
    run_autopsy()     — step-by-step replay of a recorded run
    run_duel()        — head-to-head path overlay (two algos, one maze)
    run_race()        — split-screen simultaneous replay
    run_benchmark()   — all algorithms at once with a results table
    run_multi_stats() — N runs across fresh mazes, shows min/max/mean/std

Maze persistence:
    save_maze()     — write a maze to benchmark_exports/ as .maze JSON
    load_maze()     — pick a saved .maze file and load it back
"""
from __future__ import annotations

import csv
import itertools
import json
import os
import statistics as _stats
import time
from datetime import datetime
from typing import Callable

from core.types        import RunResult, _StepRecord
from ui.theme          import *  # noqa: F401,F403
from ui.terminal_utils import clear_screen, _center_ansi, _term_width, precise_sleep
from ui.renderer       import render, render_split, CELL_RENDER
from algorithms.registry import _ALGO_NAMES, _REGISTRY, _get_generator

# These are passed to dispatch so it runs instantly with no recording
_BENCH_DELAY: float = 0.0
_BENCH_SKIP:  int   = 999_999

_EXPORT_DIR:      str = "benchmark_exports"
_SAVED_MAZES_DIR: str = "saved_mazes"


# --- BENCHMARK EXPORT ---

def _save_benchmark_export(
    results:        list[tuple[str, RunResult]],
    maze:           list[list[int | str]],
    terrain_active: bool,
    generator:      str = "dfs",
) -> tuple[str, str]:
    """Write benchmark results to CSV and the maze to JSON, both timestamped.

    CSV includes full context: complexity, generator, rows, cols, terrain.
    Returns (csv_path, maze_path).
    """
    from maze_genV4 import MAZE_SIZES

    rows, cols = len(maze), len(maze[0])
    complexity = next(
        (k for k, (r, c) in MAZE_SIZES.items() if r == rows and c == cols),
        0,
    )

    os.makedirs(_EXPORT_DIR, exist_ok=True)
    stamp     = datetime.now().strftime("%Y-%m-%d_%H-%M")
    base      = f"{stamp}_c{complexity}"
    csv_path  = os.path.join(_EXPORT_DIR, f"{base}.csv")
    maze_path = os.path.join(_EXPORT_DIR, f"{base}.maze")

    terrain_s = "true" if terrain_active else "false"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "complexity", "generator", "rows", "cols", "terrain",
            "algorithm", "steps", "time_ms", "path_len", "path_cost", "efficiency_pct",
        ])
        for name, r in results:
            if r.steps == float("inf"):
                w.writerow([complexity, generator, rows, cols, terrain_s,
                            name, "FAILED", f"{r.compute_time * 1000:.2f}", 0, 0, "—"])
            else:
                eff = f"{r.path_len / r.steps * 100:.1f}" if r.steps > 0 else "0.0"
                w.writerow([complexity, generator, rows, cols, terrain_s,
                            name, int(r.steps), f"{r.compute_time * 1000:.2f}",
                            r.path_len, r.path_cost, eff])

    maze_data = {
        "complexity": complexity, "rows": rows, "cols": cols,
        "terrain": terrain_active, "generator": generator, "grid": maze,
    }
    with open(maze_path, "w", encoding="utf-8") as f:
        json.dump(maze_data, f, separators=(",", ":"))

    return csv_path, maze_path


# --- MAZE SAVE / LOAD ---

def save_maze(
    maze:           list[list[int | str]],
    terrain_active: bool,
    generator:      str = "dfs",
) -> str | None:
    """Dump the current maze to saved_mazes/ as a .maze JSON file.

    Seconds are included in the timestamp so rapid saves don't collide.
    Returns the path it was saved to, or None if the write failed.
    """
    from maze_genV4 import MAZE_SIZES

    rows, cols = len(maze), len(maze[0])
    complexity = next(
        (k for k, (r, c) in MAZE_SIZES.items() if r == rows and c == cols),
        0,
    )

    os.makedirs(_SAVED_MAZES_DIR, exist_ok=True)

    stamp     = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    maze_path = os.path.join(_SAVED_MAZES_DIR, f"{stamp}_c{complexity}.maze")

    try:
        with open(maze_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "complexity": complexity,
                    "rows":       rows,
                    "cols":       cols,
                    "terrain":    terrain_active,
                    "generator":  generator,
                    "grid":       maze,
                },
                f,
                separators=(",", ":"),
            )
        return maze_path
    except OSError as exc:
        print(f"\n  ⚠️  Couldn't save maze: {exc}")
        return None


def load_maze() -> tuple[list[list[int | str]], bool, str] | None:
    """List all .maze files from both saved_mazes/ and benchmark_exports/,
    let the user pick one, and return (maze, terrain_active, generator).

    Searches both folders so you can reload a manually saved maze or the
    exact maze a benchmark ran on. Returns None if cancelled or no files found.
    """
    # Collect files from both dirs, labelled by source
    entries: list[tuple[str, str, dict]] = []  # (display_label, path, meta)

    for folder, tag in [(_SAVED_MAZES_DIR, "saved"), (_EXPORT_DIR, "benchmark")]:
        if not os.path.isdir(folder):
            continue
        for fname in sorted(f for f in os.listdir(folder) if f.endswith(".maze")):
            path = os.path.join(folder, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    meta = json.load(f)
                terrain_s = "terrain ON" if meta.get("terrain") else "terrain OFF"
                gen_s     = meta.get("generator", "dfs")
                label = (
                    f"  [{tag}]  {fname:<42}"
                    f"  c{meta.get('complexity', '?')}"
                    f"  {meta.get('rows', '?')}×{meta.get('cols', '?')}"
                    f"  {gen_s}  {terrain_s}"
                )
                entries.append((label, path, meta))
            except (OSError, json.JSONDecodeError):
                entries.append((f"  [{tag}]  {fname}  (unreadable)", path, {}))

    if not entries:
        print("\n  No saved mazes yet — use [s] to save one, or run a benchmark with export.")
        return None

    print("\n  Available mazes:\n")
    for i, (label, _, _) in enumerate(entries, 1):
        print(f"  {i:>2}.{label}")

    print()
    while True:
        raw = input(f"  Select (1–{len(entries)}) or 0 to cancel: ").strip()
        try:
            choice = int(raw)
        except ValueError:
            print("  Enter a number.")
            continue

        if choice == 0:
            return None

        if not (1 <= choice <= len(entries)):
            print(f"  Enter a number between 0 and {len(entries)}.")
            continue

        _, path, _ = entries[choice - 1]
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            maze = [
                [cell if isinstance(cell, str) else int(cell) for cell in row]
                for row in data["grid"]
            ]
            terrain_active = bool(data.get("terrain", False))
            generator      = data.get("generator", "dfs")
            rows, cols     = len(maze), len(maze[0])
            print(f"\n  ✅ Loaded  ({rows}×{cols}, {generator})")
            return maze, terrain_active, generator

        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            print(f"  ⚠️  Failed to read file: {exc}")
            return None



# --- ALGORITHM AUTOPSY ---

def run_autopsy(
    initial_maze: list[list[int | str]],
    recording:    list[_StepRecord],
    algo_name:    str,
) -> None:
    """Step-by-step replay of a recorded algorithm run.

    ENTER = advance one step, b = go back, <number> = jump to that step, q = quit.
    """
    if not recording:
        print(f"\n  (No steps recorded for {algo_name}.)")
        input(f"  Press {C_PATH}ENTER{C_END} to continue…")
        return

    total = len(recording)
    maze  = [row[:] for row in initial_maze]
    pos   = 0

    def _rebuild_to(target: int) -> None:
        """Replay from the beginning to *target* step. Needed for jump navigation."""
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
    print(f"\n{C_HEAD}⏮  ALGORITHM AUTOPSY — {algo_name}{C_END}\n  {total} steps recorded.\n  ENTER=next  b=back  <number>=jump  q=quit\n")
    time.sleep(0.8)

    while True:
        # Flash the frontier marker at current position
        if pos > 0:
            rec    = recording[pos - 1]
            r_head = rec.r
            c_head = rec.c
            saved  = maze[r_head][c_head] if maze[r_head][c_head] not in {'S', 'E'} else None
            if saved is not None:
                maze[r_head][c_head] = '@'
        else:
            r_head = c_head = -1
            saved  = None

        hud_text = recording[pos - 1].hud if pos > 0 else f"{algo_name} — start of run (no steps applied yet)"
        nav_line = f"⏮  Autopsy: step {pos}/{total}  [ENTER=next  b=back  <N>=jump  q=quit]"
        render(maze, f"{hud_text}\n{nav_line}")

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
                target = max(0, min(total, int(raw)))
                _rebuild_to(target)
            except ValueError:
                pass



# --- ALGORITHM DUEL ---

def run_duel(
    original_maze: list[list[int | str]],
    maze1_result:  list[list[int | str]],
    result1:       RunResult,
    algo1_name:    str,
    terrain_active: bool,
    *,
    dispatch_fn: Callable,
) -> None:
    """Show two algorithm paths on the same maze as a coloured overlay.

    Cells only in path 1 are marked '1', only in path 2 as '2', shared cells as '*'.
    """
    clear_screen()
    rows, cols = len(original_maze), len(original_maze[0])

    _max_key = max(int(s.key) for s in _REGISTRY)

    print("\n" + "═" * 62)
    print("⚔️  ALGORITHM DUEL — HEAD-TO-HEAD PATH COMPARISON".center(62))
    print("═" * 62)
    print(f"  {C_PATH}Challenger 1{C_END} : {algo1_name}  ({result1.path_len} cells, cost {result1.path_cost})")
    print(f"\n  Select {C_DUEL2}Challenger 2{C_END}:\n")
    for key, name in _ALGO_NAMES.items():
        print(f"  {key:>2}. {name}")
    print()

    while True:
        choice2 = input(f"  Challenger 2 (1-{_max_key}): ").strip()
        if choice2 in _ALGO_NAMES:
            break
        print(f"  Invalid — enter a number 1-{_max_key}.")

    algo2_name = _ALGO_NAMES[choice2]
    maze2      = [row[:] for row in original_maze]
    print(f"\n  ⏳ Running {algo2_name} (instant mode)…")

    result2 = dispatch_fn(choice2, maze2, _BENCH_DELAY, _BENCH_SKIP, None, None)

    output: list[str] = []
    shared_n = only1_n = only2_n = 0
    for ri in range(rows):
        parts: list[str] = []
        for ci in range(cols):
            orig = original_maze[ri][ci]
            p1   = (maze1_result[ri][ci] == 'P')
            p2   = (maze2[ri][ci]         == 'P')
            if orig == 1:
                parts.append(f"{C_WALL}█{C_END}")
            elif orig in {'S', 'E'}:
                parts.append(f"{C_START}{orig}{C_END}")
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
                parts.append(CELL_RENDER.get(orig, " "))
        output.append("".join(parts))

    clear_screen()
    print(f"\n⚔️  DUEL: {C_PATH}{algo1_name}{C_END}  vs  {C_DUEL2}{algo2_name}{C_END}\n")
    print("\n".join(output))

    W  = 62
    f1 = result1.steps == float('inf')
    f2 = result2.steps == float('inf')

    def _fmt(val: float, failed: bool) -> str:
        return "FAILED" if failed else str(int(val))

    print("\n" + "─" * W)
    print(f"  {'Metric':<22} {algo1_name:<18} {algo2_name:<18}")
    print("─" * W)
    print(f"  {'Steps':<22} {_fmt(result1.steps, f1):<18} {_fmt(result2.steps, f2):<18}")
    print(f"  {'Path Length':<22} {result1.path_len:<18} {result2.path_len:<18}")
    if terrain_active:
        print(f"  {'Path Cost':<22} {result1.path_cost:<18} {result2.path_cost:<18}")
    print(f"  {'Compute Time':<22} {result1.compute_time * 1000:.2f} ms{'':<10} {result2.compute_time * 1000:.2f} ms")
    print("─" * W)
    print(f"  {C_PATH}1{C_END}={algo1_name} only ({only1_n})   {C_DUEL2}2{C_END}={algo2_name} only ({only2_n})   {C_HEAD}*{C_END}=shared ({shared_n})")
    print("─" * W)



# --- RACE MODE ---

def run_race(
    original_maze: list[list[int | str]],
    delay:         float,
    skip_frames:   int,
    terrain_active: bool,
    fog_mode:      bool = False,
    *,
    dispatch_fn:     Callable,
    start_recording: Callable,
    stop_recording:  Callable,
) -> None:
    """Run two algorithms side-by-side in a split terminal.

    Both are pre-run in instant mode to capture step recordings, then replayed
    together one frame at a time so they race in sync.
    """
    rows, cols  = len(original_maze), len(original_maze[0])
    required_w  = cols * 2 + 7

    try:
        term = os.get_terminal_size()
        if term.columns < required_w:
            print(
                f"\n  ⚠️  Race Mode requires ≥ {required_w} terminal columns.\n"
                f"  Your terminal : {term.columns} columns wide.\n"
                f"  Each maze is  : {cols} columns wide.\n"
                f"  → Regenerate at a lower complexity (≤ 4), or widen your terminal."
            )
            input(f"\n  Press {C_PATH}ENTER{C_END} to abort race.")
            return
    except OSError:
        pass  # can't detect terminal size — proceed anyway

    clear_screen()
    _RW = _term_width()
    print("\n" + "═" * _RW)
    print(_center_ansi("🏎️   RACE MODE — TWO ALGORITHMS, ONE MAZE, SIDE-BY-SIDE  🏎️", _RW))
    print("═" * _RW)
    print("  Both algorithms run on identical copies of the current maze.")
    print("  They are pre-run instantly, then replayed together frame-by-frame.")
    if fog_mode:
        print(
            f"\n  {C_BACK}🌫  Note: Fog of War is ON but is not applied in Race Mode.{C_END}\n"
            "  Race pre-runs use instant mode — fog would conceal nothing useful.\n"
            "  The full maze is shown so both search frontiers are comparable."
        )
    print()

    _max_key = max(int(s.key) for s in _REGISTRY)

    print(f"  {C_PATH}Select Challenger 1:{C_END}\n")
    for key, name in _ALGO_NAMES.items():
        print(f"  {key:>2}. {name}")
    print()
    while True:
        c1 = input(f"  Challenger 1 (1-{_max_key}): ").strip()
        if c1 in _ALGO_NAMES:
            break
        print(f"  Please enter a number 1–{_max_key}.")

    print(f"\n  {C_DUEL2}Select Challenger 2:{C_END}\n")
    for key, name in _ALGO_NAMES.items():
        print(f"  {key:>2}. {name}")
    print()
    while True:
        c2 = input(f"  Challenger 2 (1-{_max_key}): ").strip()
        if c2 in _ALGO_NAMES:
            break
        print(f"  Please enter a number 1–{_max_key}.")

    name1, name2 = _ALGO_NAMES[c1], _ALGO_NAMES[c2]

    print(f"\n  ⏳ Pre-running {name1}…")
    maze_run1: list[list[int | str]] = [row[:] for row in original_maze]
    vc1: dict[tuple[int, int], int]  = {}
    start_recording()
    try:
        result1 = dispatch_fn(c1, maze_run1, _BENCH_DELAY, _BENCH_SKIP, None, vc1)
    finally:
        rec1 = stop_recording()

    print(f"  ⏳ Pre-running {name2}…")
    maze_run2: list[list[int | str]] = [row[:] for row in original_maze]
    vc2: dict[tuple[int, int], int]  = {}
    start_recording()
    try:
        result2 = dispatch_fn(c2, maze_run2, _BENCH_DELAY, _BENCH_SKIP, None, vc2)
    finally:
        rec2 = stop_recording()

    total1, total2 = len(rec1), len(rec2)
    if total1 == 0 and total2 == 0:
        print("\n  (No steps recorded — cannot replay race.)")
        input(f"\n  Press {C_PATH}ENTER{C_END} to continue.")
        return

    if total1 == 0:
        print(
            f"\n  {C_HEAD}⚠ {name1} uses pass-level rendering — no per-cell replay available.\n"
            f"  Left pane will show as instantly complete.{C_END}"
        )
    if total2 == 0:
        print(
            f"\n  {C_HEAD}⚠ {name2} uses pass-level rendering — no per-cell replay available.\n"
            f"  Right pane will show as instantly complete.{C_END}"
        )

    print(f"\n  {name1}: {total1} steps recorded.")
    print(f"  {name2}: {total2} steps recorded.")
    print(f"\n  {C_RACE}▶  Starting race replay…{C_END}")
    time.sleep(0.8)

    replay1: list[list[int | str]] = [row[:] for row in original_maze]
    replay2: list[list[int | str]] = [row[:] for row in original_maze]
    pos1, pos2 = 0, 0
    race_skip  = max(skip_frames, 1)
    race_delay = delay

    while pos1 < total1 or pos2 < total2:
        for _ in range(race_skip):
            if pos1 < total1:
                rec = rec1[pos1]
                replay1[rec.r][rec.c] = rec.new_cell
                pos1 += 1
            if pos2 < total2:
                rec = rec2[pos2]
                replay2[rec.r][rec.c] = rec.new_cell
                pos2 += 1

        # Stamp transient frontier markers then render, then restore
        head1_r = head1_c = head2_r = head2_c = -1
        saved1: int | str | None = None
        saved2: int | str | None = None

        if 0 < pos1 <= total1:
            last1 = rec1[pos1 - 1]
            head1_r, head1_c = last1.r, last1.c
            if replay1[head1_r][head1_c] not in {'S', 'E'}:
                saved1 = replay1[head1_r][head1_c]
                replay1[head1_r][head1_c] = '@'

        if 0 < pos2 <= total2:
            last2 = rec2[pos2 - 1]
            head2_r, head2_c = last2.r, last2.c
            if replay2[head2_r][head2_c] not in {'S', 'E'}:
                saved2 = replay2[head2_r][head2_c]
                replay2[head2_r][head2_c] = '@'

        render_split(replay1, replay2, name1, name2, pos1, pos2, total1, total2)

        if saved1 is not None:
            replay1[head1_r][head1_c] = saved1
        if saved2 is not None:
            replay2[head2_r][head2_c] = saved2
        if race_delay > 0:
            precise_sleep(race_delay)

    # Copy solution paths from the pre-run mazes into the replay mazes for
    # the final frame — reconstruct_path() writes 'P' directly to the maze
    # without going through animate_step(), so the recording doesn't have them
    for ri in range(rows):
        for ci in range(cols):
            if maze_run1[ri][ci] == 'P':
                replay1[ri][ci] = 'P'
            if maze_run2[ri][ci] == 'P':
                replay2[ri][ci] = 'P'

    render_split(replay1, replay2, name1, name2, total1, total2, total1, total2)

    W  = 70
    f1 = result1.steps == float('inf')
    f2 = result2.steps == float('inf')
    print("\n" + "═" * W)
    print("🏁  RACE RESULTS  🏁".center(W))
    print("═" * W)
    print(f"  {'Metric':<22} {C_PATH}{name1:<20}{C_END} {C_DUEL2}{name2:<20}{C_END}")
    print("─" * W)

    def _fmt(val: float, failed: bool) -> str:
        return "FAILED" if failed else str(int(val))

    print(f"  {'Steps':<22} {_fmt(result1.steps, f1):<20} {_fmt(result2.steps, f2):<20}")
    print(f"  {'Path Length':<22} {result1.path_len:<20} {result2.path_len:<20}")
    if terrain_active:
        print(f"  {'Path Cost':<22} {result1.path_cost:<20} {result2.path_cost:<20}")
    print(f"  {'Compute Time':<22} {result1.compute_time * 1000:<20.2f} {result2.compute_time * 1000:<20.2f}")
    print("─" * W)

    if not f1 and not f2:
        if terrain_active:
            if result1.path_cost < result2.path_cost:
                print(f"\n  🏆 {C_PATH}{name1} WINS{C_END} on path cost ({result1.path_cost} vs {result2.path_cost})")
            elif result2.path_cost < result1.path_cost:
                print(f"\n  🏆 {C_DUEL2}{name2} WINS{C_END} on path cost ({result2.path_cost} vs {result1.path_cost})")
            else:
                print(f"\n  🤝 DEAD TIE on path cost!  ({result1.path_cost} cells weighted)")
        else:
            if result1.path_len < result2.path_len:
                print(f"\n  🏆 {C_PATH}{name1} WINS{C_END} on path length ({result1.path_len} vs {result2.path_len} hops)")
            elif result2.path_len < result1.path_len:
                print(f"\n  🏆 {C_DUEL2}{name2} WINS{C_END} on path length ({result2.path_len} vs {result1.path_len} hops)")
            elif result1.steps < result2.steps:
                print(f"\n  🤝 EQUAL paths — {C_PATH}{name1}{C_END} found it more efficiently")
            else:
                print(f"\n  🤝 DEAD TIE — identical path and identical search effort.")
    elif not f1 and f2:
        print(f"\n  🏆 {C_PATH}{name1} WINS!{C_END}  {name2} failed to find a path.")
    elif not f2 and f1:
        print(f"\n  🏆 {C_DUEL2}{name2} WINS!{C_END}  {name1} failed to find a path.")
    else:
        print(f"\n  💀 Both algorithms FAILED on this maze. Nobody wins.")
    print("═" * W)
    input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")



def _print_bar_chart(results: list[tuple[str, RunResult]]) -> None:
    """Print an ASCII bar chart of steps for each algorithm.

    The longest bar = the algorithm with the most steps (100%).
    Failed runs show at the bottom without a bar.
    Keeps things visual — the table above has the exact numbers,
    this just makes the relative differences jump out.
    """
    BAR_WIDTH   = 32
    NAME_WIDTH  = 14

    solved  = [(n, r) for n, r in results if r.steps != float('inf')]
    failed  = [(n, r) for n, r in results if r.steps == float('inf')]

    if not solved:
        return

    max_steps = max(r.steps for _, r in solved)

    print(f"\n  {C_BIGO}Steps — search effort (lower = explored less){C_END}\n")
    for name, r in sorted(solved, key=lambda x: x[1].steps):
        filled = round(r.steps / max_steps * BAR_WIDTH)
        empty  = BAR_WIDTH - filled
        bar    = f"{C_PATH}{'█' * filled}{C_END}{C_DOT}{'░' * empty}{C_END}"
        print(f"  {name:<{NAME_WIDTH}} {bar}  {int(r.steps)}")

    for name, _ in failed:
        print(f"  {name:<{NAME_WIDTH}} {C_BACK}FAILED{C_END}")

    print()


# --- BENCHMARK ---

def run_benchmark(
    original_maze: list[list[int | str]],
    delay:         float,
    skip_frames:   int,
    terrain_active: bool,
    *,
    generator:   str = "dfs",
    dispatch_fn: Callable,
) -> None:
    """Run all algorithms on the current maze and print a comparison table."""
    clear_screen()
    rows, cols  = len(original_maze), len(original_maze[0])
    total_cells = rows * cols
    print("\n" + "═" * 82)
    print("⏳  BENCHMARK CONFIGURATION  ⏳".center(82))
    print("═" * 82)
    print(f"  Maze: {rows} × {cols}  ({total_cells} cells)")
    print("  All algorithms run instantly with animation and recording disabled.\n")

    # Build the list of algorithms to run.
    # Slow ones (Random Mouse) get an opt-in prompt so they don't silently
    # chew up benchmark time on large mazes.
    bench_choices: list[tuple[str, str]] = [
        (s.bench_name, s.key) for s in _REGISTRY if not s.bench_slow_warn
    ]
    for _bspec in [s for s in _REGISTRY if s.bench_slow_warn]:
        _include = True
        if _bspec.bench_warn_cells == 0 or total_cells > _bspec.bench_warn_cells:
            while True:
                ans = input(f"\n  Include '{_bspec.display_name}'? (y/n): ").strip().lower()
                if ans in {'y', 'yes', 'n', 'no'}:
                    break
            _include = ans in {'y', 'yes'}
        if _include:
            bench_choices.append((_bspec.bench_name, _bspec.key))

    print("\n⏳ Starting Benchmark… Please wait.\n")
    time.sleep(0.5)

    results: list[tuple[str, RunResult]] = []
    for name, choice in bench_choices:
        maze_copy = [row[:] for row in original_maze]
        result    = dispatch_fn(choice, maze_copy, _BENCH_DELAY, _BENCH_SKIP, None, None)
        results.append((name, result))
        print(f"  ✔ {name} done.")

    clear_screen()
    cost_hdr = "PATH COST" if terrain_active else "PATH LEN"
    W        = 82
    print("\n" + "═" * W)
    print("🏆  FINAL BENCHMARK RESULTS  🏆".center(W))
    print("═" * W)
    print(f"| {'ALGORITHM':<14} | {'STEPS':<13} | {'TIME (ms)':<10} | {cost_hdr:<10} | {'EFFICIENCY':<10} |")
    print("-" * W)

    # Sort by path cost (terrain) or steps (no terrain).
    # Failed runs go to the bottom.
    sort_key = (
        (lambda x: x[1].path_cost if x[1].steps != float('inf') else float('inf'))
        if terrain_active
        else (lambda x: x[1].steps)
    )
    for name, r in sorted(results, key=sort_key):
        steps_s = str(int(r.steps)) if r.steps != float('inf') else "FAILED"
        cost_s  = str(r.path_cost)  if r.steps != float('inf') else "—"
        eff_s   = (
            f"{r.path_len / r.steps * 100:.1f}%"
            if r.steps not in {0, float('inf')} else "—"
        )
        print(f"| {name:<14} | {steps_s:<13} | {r.compute_time * 1000:<10.2f} | {cost_s:<10} | {eff_s:<10} |")

    print("═" * W)
    print(
        f"\n  {C_STAT}📊 KEY INSIGHTS:{C_END}\n"
        "  STEPS  = search effort (nodes expanded) — lower ≠ better path.\n"
        "  PATH   = solution length — this is what actually matters.\n"
        "  EFFICIENCY = Path ÷ Steps — IDA* is low by design.\n"
    )

    _print_bar_chart(results)

    # Ask about export before the ENTER prompt so you can choose without
    # having to re-run the whole benchmark
    while True:
        save_ans = input("  💾 Save results to CSV? (y/n): ").strip().lower()
        if save_ans in {"y", "yes", "n", "no"}:
            break

    if save_ans in {"y", "yes"}:
        try:
            csv_path, maze_path = _save_benchmark_export(results, original_maze, terrain_active, generator)
            print(f"\n  ✅ Saved to {C_PATH}{_EXPORT_DIR}/{C_END}")
            print(f"     {csv_path}")
            print(f"     {maze_path}")
        except Exception as exc:
            print(f"\n  ⚠️  Export failed: {exc}")

    input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")

# --- MULTI-RUN STATISTICS ---

def run_multi_stats(dispatch_fn: Callable, generator: str = "dfs") -> None:
    """Run selected algorithms N times on fresh mazes and report statistics.

    Each run generates a new maze so the results reflect performance across
    many different layouts, not just one lucky or unlucky maze.
    """
    from maze_genV4 import generate_maze, MAZE_SIZES

    _SIZE_LABELS = {
        0: "tiny",   1: "tiny",   2: "small",  3:  "small",
        4: "medium", 5: "medium", 6: "large",  7:  "large",
        8: "huge",   9: "huge",  10: "massive",
    }
    W = _term_width()

    # --- algorithm selection ---
    clear_screen()
    print(f"\n  {C_BIGO}📊  MULTI-RUN STATISTICS{C_END}\n")
    print("  Which algorithms to include?\n")

    specs = list(_REGISTRY)
    col1, col2 = specs[:8], specs[8:]
    for i, s1 in enumerate(col1):
        star1 = "★" if (s1.cost_optimal or s1.hop_optimal) else " "
        left  = f"  {s1.key:>2}. {s1.display_name:<20} {star1}"
        right = ""
        if i < len(col2):
            s2    = col2[i]
            star2 = "★" if (s2.cost_optimal or s2.hop_optimal) else " "
            right = f"  {s2.key:>2}. {s2.display_name:<20} {star2}"
        print(f"{left}{right}")

    print()
    while True:
        raw = input('  Numbers (e.g. "1,3,5") or "all": ').strip().lower()
        if raw == "all":
            selected = specs
            break
        try:
            keys     = {p.strip() for p in raw.split(",")}
            selected = [s for s in specs if s.key in keys]
            if selected:
                break
            print("  No valid numbers — try again.")
        except Exception:
            print("  Invalid input.")

    print(f"\n  {C_DOT}Selected: {', '.join(s.display_name for s in selected)}{C_END}")

    # --- N runs ---
    print("\n  Runs per algorithm:")
    print("    1)  5     2) 10     3) 20     4) 50     5) custom")
    _RUN_PRESETS = {"1": 5, "2": 10, "3": 20, "4": 50}
    while True:
        rc = input("  → ").strip()
        if rc in _RUN_PRESETS:
            N = _RUN_PRESETS[rc]
            break
        if rc == "5":
            try:
                N = int(input("  Custom N: ").strip())
                if N > 0:
                    break
                print("  Must be positive.")
            except ValueError:
                print("  Enter a number.")
            continue
        print("  Enter 1–5.")

    # --- complexity mode ---
    print("\n  Complexity mode:")
    print("    a) Single level — same maze size every run")
    print("    b) Multi level  — rotate through levels you pick")
    while True:
        mode = input("  → ").strip().lower()
        if mode in {"a", "b"}:
            break
        print("  Enter a or b.")

    # Show the complexity table in two columns so it's readable
    print("\n  Complexity levels:\n")
    items = list(MAZE_SIZES.items())
    half  = (len(items) + 1) // 2
    for i in range(half):
        l  = items[i]
        r  = items[i + half] if i + half < len(items) else None
        lf = f"  {l[0]:>2}  →  {l[1][0]:>2}×{l[1][1]:<3}  ({_SIZE_LABELS[l[0]]})"
        rf = f"  {r[0]:>2}  →  {r[1][0]:>2}×{r[1][1]:<3}  ({_SIZE_LABELS[r[0]]})" if r else ""
        print(f"{lf:<34}{rf}")

    print()
    if mode == "a":
        while True:
            try:
                comp = int(input("  Level (0–10): ").strip())
                if 0 <= comp <= 10:
                    complexities = [comp]
                    break
                print("  Enter 0–10.")
            except ValueError:
                print("  Enter a number.")
    else:
        while True:
            raw = input("  Levels, comma-separated (e.g. 3,5,7): ").strip()
            try:
                comps = [int(x.strip()) for x in raw.split(",")]
                if comps and all(0 <= c <= 10 for c in comps):
                    complexities = comps
                    break
                print("  Each level must be 0–10.")
            except ValueError:
                print("  Numbers only, separated by commas.")

    # --- run all ---
    total = len(selected) * N
    done  = 0

    # per-algorithm step lists — float('inf') for failed runs
    step_log: dict[str, list[float]] = {s.display_name: [] for s in selected}

    print(f"\n  Running {len(selected)} × {N} = {total} runs…\n")

    for algo in selected:
        fn = _get_generator(algo.module_name)
        # fresh cycle per algorithm so every algo gets the same complexity sequence
        comp_seq = itertools.cycle(complexities)

        for run_idx in range(N):
            comp = next(comp_seq)
            maze = generate_maze(comp, generator)

            # run headless — we only want the final result
            result_steps = float('inf')
            for state in fn(maze):
                if state["type"] == "done":
                    result_steps = state["result"].steps
                    break

            step_log[algo.display_name].append(result_steps)
            done += 1

            bar_n  = 28
            filled = int(done / total * bar_n)
            bar    = f"{C_PATH}{'█' * filled}{C_END}{'░' * (bar_n - filled)}"
            print(
                f"\r  [{bar}]  {done}/{total}"
                f"  {C_DIM}{algo.display_name}  run {run_idx + 1}/{N}{C_END}",
                end="", flush=True,
            )

    print()  # end the progress line

    # --- results table ---
    clear_screen()
    comps_str = ", ".join(str(c) for c in complexities)
    print(f"\n  {C_BIGO}📊 MULTI-RUN STATISTICS{C_END}"
          f"  |  N={N}  |  Complexity: {comps_str}\n")

    hdr = f"  {'Algorithm':<22} {'Min':>6} {'Max':>6} {'Mean':>7} {'Std':>6}   Rate"
    sep = "  " + "─" * (len(hdr) - 2)
    print(hdr)
    print(sep)

    agg_rows: list[tuple] = []
    for s in selected:
        name = s.display_name
        runs = step_log[name]
        ok   = [v for v in runs if v != float('inf')]

        if ok:
            mn   = int(min(ok))
            mx   = int(max(ok))
            mean = int(_stats.mean(ok))
            std  = int(_stats.stdev(ok)) if len(ok) > 1 else 0
            rate = f"{len(ok)}/{N}"
            clr  = C_BACK if len(ok) < N else C_END
            print(f"  {clr}{name:<22}{C_END} {mn:>6} {mx:>6} {mean:>7} {std:>6}   {rate}")
        else:
            mn = mx = mean = std = None
            rate = f"0/{N}"
            print(f"  {C_DIM}{name:<22}{'—':>6} {'—':>6} {'—':>7} {'—':>6}   {rate}{C_END}")

        agg_rows.append((name, mn, mx, mean, std, len(ok), N))

    print(sep)

    # --- CSV export ---
    print()
    while True:
        save_ans = input("  💾 Save to CSV? (y/n): ").strip().lower()
        if save_ans in {"y", "yes", "n", "no"}:
            break

    if save_ans in {"y", "yes"}:
        os.makedirs(_EXPORT_DIR, exist_ok=True)
        stamp    = datetime.now().strftime("%Y-%m-%d_%H-%M")
        tag      = comps_str.replace(", ", "_")
        path     = os.path.join(_EXPORT_DIR, f"{stamp}_stats_c{tag}_N{N}.csv")
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["algorithm", "min", "max", "mean", "std",
                            "successes", "runs", "success_rate"])
                for name, mn, mx, mean, std, ok_c, total_n in agg_rows:
                    pct = f"{ok_c / total_n * 100:.0f}%"
                    w.writerow([
                        name,
                        mn   if mn   is not None else "FAILED",
                        mx   if mx   is not None else "FAILED",
                        mean if mean is not None else "FAILED",
                        std  if std  is not None else "FAILED",
                        ok_c, total_n, pct,
                    ])
            print(f"\n  ✅ Saved to {C_PATH}{path}{C_END}")
        except OSError as exc:
            print(f"\n  ⚠️  Couldn't write CSV: {exc}")

    input(f"\n👉 Press {C_PATH}ENTER{C_END} to continue…")