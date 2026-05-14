"""
maze_modes.py — interactive post-run and system modes.

The four modes extracted from the old monolith:
    run_autopsy()   — step-by-step replay of a recorded run
    run_duel()      — head-to-head path overlay (two algos, one maze)
    run_race()      — split-screen simultaneous replay
    run_benchmark() — all algorithms at once with a results table
"""
from __future__ import annotations

import os
import time
from typing import Callable

from core.types        import RunResult, _StepRecord
from ui.theme          import *  # noqa: F401,F403
from ui.terminal_utils import clear_screen, _center_ansi, _term_width, precise_sleep
from ui.renderer       import render, render_split, CELL_RENDER
from algorithms.registry import _ALGO_NAMES, _REGISTRY

# These are passed to dispatch so it runs instantly with no recording
_BENCH_DELAY: float = 0.0
_BENCH_SKIP:  int   = 999_999



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



# --- BENCHMARK ---

def run_benchmark(
    original_maze: list[list[int | str]],
    delay:         float,
    skip_frames:   int,
    terrain_active: bool,
    *,
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
    input(f"👉 Press {C_PATH}ENTER{C_END} to continue…")
