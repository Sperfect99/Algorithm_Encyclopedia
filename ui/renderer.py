"""
ui/renderer.py — all the maze drawing happens here.

Pure rendering: builds ANSI strings and writes them in one syscall.
No algorithm logic, no sleeping, no input().
"""
from __future__ import annotations

from itertools import zip_longest

from ui.theme import (
    C_WALL, C_DOT, C_BACK, C_HEAD, C_PATH, C_START, C_MUD, C_FOG,
    C_DUEL2, C_END,
    AGENT_COLORS, GOAL_COLORS, C_CONFLICT, C_TARGET, C_INTERCEPT,
    C_TREASURE, C_COLLECTED, C_GA_LIVE, C_STAT, C_DIM,
)
import sys as _sys

from ui.terminal_utils import (
    clear_screen, _strip_ansi, _visual_width, PROGRESS_BAR_WIDTH,
)

# Minimum cost improvement before showing the "▼N improved" delta badge in GA overlay.
# Below this threshold we treat it as floating-point noise.
_GA_IMPROVEMENT_THRESHOLD: float = 0.5


def _render_frame(*sections: str) -> None:
    """Write an entire TUI frame to stdout in one syscall.

    Concatenates clear-screen escape + all non-empty sections + SGR reset,
    then flushes. One write call eliminates partial-frame repaints that happen
    when multiple print() calls span an OS scheduler tick.
    """
    try:
        if not _sys.stdout.isatty():
            return
    except AttributeError:
        return
    # \033[3J = erase scrollback, \033[2J = erase viewport, \033[H = cursor home
    buf = "\033[3J\033[2J\033[H" + "\n".join(s for s in sections if s) + "\033[0m"
    try:
        _sys.stdout.write(buf)
        _sys.stdout.flush()
    except (OSError, BrokenPipeError):
        pass



# --- CELL RENDER MAPS ---

CELL_RENDER: dict[int | str, str] = {
    1:   f"{C_WALL}█{C_END}",
    '.': f"{C_DOT}.{C_END}",
    'x': f"{C_BACK}×{C_END}",
    '@': f"{C_HEAD}●{C_END}",
    'P': f"{C_PATH}P{C_END}",
    'S': f"{C_START}S{C_END}",
    'E': f"{C_START}E{C_END}",
    '~': f"{C_MUD}~{C_END}",
    0:   " ",
}

# Used by render_tsp only — extends CELL_RENDER with Treasure domain cells
TSP_CELL_RENDER: dict[int | str, str] = {
    **CELL_RENDER,
    'T': f"{C_TREASURE}T{C_END}",    # uncollected treasure
    'c': f"{C_COLLECTED}*{C_END}",   # collected treasure
    'g': f"{C_GA_LIVE}·{C_END}",     # GA ghost-path overlay cell
}

# 10 entries covers the controller's max of 10 agents with no modulo collision
_AGENT_GLYPHS: tuple[str, ...] = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")
_GOAL_GLYPHS:  tuple[str, ...] = ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")



# --- HEATMAP GRADIENT ---

# Absolute tiers so the same colour always means the same visit count,
# regardless of run. Students can compare heatmaps across algorithms.
_HEAT_TIERS: tuple[tuple[int, str], ...] = (
    (1,  "\033[38;5;21m"),   # Blue   — visited exactly once
    (2,  "\033[38;5;51m"),   # Cyan   — revisited once
    (4,  "\033[38;5;82m"),   # Green  — moderate revisiting
    (9,  "\033[38;5;226m"),  # Yellow — frequently revisited
    (19, "\033[38;5;208m"),  # Orange — algorithm is looping here
)
_HEAT_MAX_COLOR: str = "\033[38;5;196m"  # Red — 20+ visits, pathological


def _heat_escape(count: int) -> str:
    for threshold, code in _HEAT_TIERS:
        if count <= threshold:
            return code
    return _HEAT_MAX_COLOR



# --- render() ---

def render(
    maze:    list[list[int | str]],
    message: str = "",
    fog:     set[tuple[int, int]] | None = None,
) -> None:
    """Single-pane maze render with ANSI colours."""
    output: list[str] = []
    for ri, row in enumerate(maze):
        parts: list[str] = []
        for ci, cell in enumerate(row):
            if (
                fog is not None
                and cell not in {1, 'S', 'E'}
                and (ri, ci) not in fog
            ):
                parts.append(f"{C_FOG}█{C_END}")
            else:
                parts.append(CELL_RENDER.get(cell, str(cell)))
        output.append("".join(parts))

    legend = (
        f"  {C_START}S{C_END}=start  {C_START}E{C_END}=exit  "
        f"{C_HEAD}●{C_END}=frontier  {C_DOT}·{C_END}=visited  "
        f"{C_PATH}P{C_END}=solution  {C_MUD}~{C_END}=mud(cost 3)"
    )
    fog_line = (
        f"{C_BACK}🌫  FOG OF WAR{C_END}  "
        f"{C_DOT}Revealed: {len(fog)} cells{C_END}"
        if fog is not None else ""
    )
    _render_frame(legend, fog_line, "\n".join(output), f"\n{message}")



# --- render_split() — Race Mode ---

def render_split(
    maze1:  list[list[int | str]],
    maze2:  list[list[int | str]],
    name1:  str,
    name2:  str,
    step1:  int,
    step2:  int,
    total1: int,
    total2: int,
) -> None:
    """Render two maze states side-by-side for Race Mode."""
    cols = len(maze1[0])

    def _lines(maze: list[list[int | str]]) -> list[str]:
        return [
            "".join(CELL_RENDER.get(cell, str(cell)) for cell in row)
            for row in maze
        ]

    lines1 = _lines(maze1)
    lines2 = _lines(maze2)

    done1 = step1 >= total1
    done2 = step2 >= total2

    # Use » (U+00BB) not ⚡ (U+26A1) — ⚡ is ambiguous-width and causes
    # the │ divider to drift 1 column right on most terminals
    status1 = (
        f"{C_PATH}✅ DONE ({total1} steps){C_END}" if done1
        else f"{C_HEAD}» step {step1}{C_END}"
    )
    status2 = (
        f"{C_PATH}✅ DONE ({total2} steps){C_END}" if done2
        else f"{C_HEAD}» step {step2}{C_END}"
    )

    n1 = name1[: cols - 2] if len(name1) > cols - 2 else name1
    n2 = name2[: cols - 2] if len(name2) > cols - 2 else name2

    vis_status1 = _strip_ansi(status1)
    vis_n1      = _strip_ansi(n1)
    header_pad  = max(0, cols - _visual_width(vis_n1) - 2)
    status_pad  = max(0, cols - _visual_width(vis_status1) - 2)

    header_row = (
        f"{C_PATH}◀ {n1}{C_END}" + " " * header_pad + "  │  " + f"{C_DUEL2}▶ {n2}{C_END}"
    )
    status_row = (
        f"  {status1}" + " " * status_pad + "  │  " + f"  {status2}"
    )
    divider = "─" * cols + "──┼──" + "─" * cols
    grid    = "\n".join(f"{l1}  │  {l2}" for l1, l2 in zip_longest(lines1, lines2, fillvalue=" " * cols))
    _render_frame(header_row, status_row, divider, grid)



# --- render_heatmap() ---

def render_heatmap(
    visit_count: dict[tuple[int, int], int],
    maze:        list[list[int | str]],
    algo_name:   str,
) -> None:
    """Render a 256-colour exploration heatmap using absolute visit-count tiers."""
    if not visit_count:
        print("  (No exploration data — run with animation to generate heatmap.)")
        return

    max_visits  = max(visit_count.values())
    rows, cols  = len(maze), len(maze[0])
    output: list[str] = []

    for ri, row in enumerate(maze):
        parts: list[str] = []
        for ci, cell in enumerate(row):
            pos = (ri, ci)
            if cell == 1:
                parts.append(f"{C_WALL}█{C_END}")
            elif cell == 'P':
                parts.append(f"{C_PATH}P{C_END}")
            elif cell in {'S', 'E'}:
                parts.append(f"{C_START}{cell}{C_END}")
            elif pos in visit_count:
                color = _heat_escape(visit_count[pos])
                parts.append(f"{color}█{C_END}")
            else:
                parts.append(" ")
        output.append("".join(parts))

    heading     = f"\n{C_HEAD}🌡️  EXPLORATION HEATMAP — {algo_name}{C_END}"
    legend_line = (
        f"  {C_WALL}Wall{C_END}  "
        f"\033[38;5;21m█{C_END}1×  "
        f"\033[38;5;51m█{C_END}2×  "
        f"\033[38;5;82m█{C_END}3-4×  "
        f"\033[38;5;226m█{C_END}5-9×  "
        f"\033[38;5;208m█{C_END}10-19×  "
        f"{_HEAT_MAX_COLOR}█{C_END}20+×"
        f"  ← visit count tiers   {C_PATH}P{C_END}=solution path"
        f"  |  peak: {max_visits}×"
    )
    reexpansion_note = (
        f"\n  {C_DIM}High visit counts on IDA* reflect threshold re-expansions,\n"
        f"  not separate exploration passes — each bounded DFS restarts from S.{C_END}"
        if algo_name == "IDA*" and max_visits > 5 else ""
    )
    stats = (
        f"\n  Peak visits on single cell : {max_visits}"
        f"  |  Total cells explored : {len(visit_count)}"
        f"  |  Maze size : {rows}×{cols}"
        f"{reexpansion_note}"
    )
    _render_frame(heading, legend_line, "\n".join(output), stats)



# --- render_mapf() — MAPF overlay ---

def render_mapf(
    maze:      list[list[int | str]],
    positions: list[tuple[int, int]],
    goals:     list[tuple[int, int]],
    conflicts: list[tuple[int, int]],
    paths:     list[list[tuple[int, int]]] | None,
    message:   str = "",
) -> None:
    """Render a multi-agent MAPF state.

    Overlay priority (highest wins):
        1. Conflict cell  → red '!'
        2. Agent position → coloured digit
        3. Goal position  → coloured letter (if unoccupied by agent)
        4. Path cell      → grey '·'
        5. Standard cell  → CELL_RENDER
    """
    rows, cols = len(maze), len(maze[0])
    n_agents   = len(positions)

    pos_map:      dict[tuple[int, int], int] = {}
    goal_map:     dict[tuple[int, int], int] = {}
    path_cells:   set[tuple[int, int]]       = set()
    conflict_set: set[tuple[int, int]]       = set(conflicts)

    at_goal_set: set[int] = set()
    for i, pos in enumerate(positions):
        pos_map[pos] = i
        if goals and i < len(goals) and pos == goals[i]:
            at_goal_set.add(i)
    for i, goal in enumerate(goals):
        if goal not in pos_map:
            goal_map[goal] = i
    if paths:
        for path in paths:
            for cell in path[1:]:
                path_cells.add(cell)

    output: list[str] = []
    for ri, row in enumerate(maze):
        parts: list[str] = []
        for ci, cell in enumerate(row):
            coord = (ri, ci)
            if cell == 1:
                parts.append(f"{C_WALL}█{C_END}")
            elif coord in conflict_set:
                parts.append(f"{C_CONFLICT}!{C_END}")
            elif coord in pos_map:
                idx   = pos_map[coord]
                color = AGENT_COLORS[idx % len(AGENT_COLORS)]
                glyph = _AGENT_GLYPHS[idx % len(_AGENT_GLYPHS)]
                parts.append(f"{color}{glyph}{C_END}")
            elif coord in goal_map:
                idx   = goal_map[coord]
                color = GOAL_COLORS[idx % len(GOAL_COLORS)]
                glyph = _GOAL_GLYPHS[idx % len(_GOAL_GLYPHS)]
                parts.append(f"{color}{glyph}{C_END}")
            elif coord in path_cells and cell not in {'S', 'E'}:
                parts.append(f"{C_DOT}·{C_END}")
            elif cell in {'S', 'E'}:
                parts.append(f"{C_START}{cell}{C_END}")
            elif cell == '~':
                parts.append(f"{C_MUD}~{C_END}")
            else:
                parts.append(" ")
        output.append("".join(parts))

    legend_parts: list[str] = []
    for i in range(n_agents):
        color  = AGENT_COLORS[i % len(AGENT_COLORS)]
        glyph  = _AGENT_GLYPHS[i % len(_AGENT_GLYPHS)]
        gcol   = GOAL_COLORS[i % len(GOAL_COLORS)]
        gglyph = _GOAL_GLYPHS[i % len(_GOAL_GLYPHS)]
        legend_parts.append(f"{color}{glyph}{C_END}=A{i}  {gcol}{gglyph}{C_END}=G{i}")
    legend_parts.append(f"{C_CONFLICT}!{C_END}=conflict")
    legend_line = "  " + "   ".join(legend_parts)
    _render_frame(legend_line, "\n".join(output), f"\n{message}")



# --- render_pursuit() — Pursuit/Pac-Man overlay ---

def render_pursuit(
    maze:        list[list[int | str]],
    agent_pos:   tuple[int, int],
    target_pos:  tuple[int, int],
    path:        list[tuple[int, int]],
    intercept:   tuple[int, int] | None,
    message:     str = "",
    extra_walls: set[tuple[int, int]] | None = None,
) -> None:
    """Render a dynamic pursuit state.

    Overlay priority: dynamic wall > agent > target > intercept > path > standard cell.
    """
    extra_walls = extra_walls or set()
    path_set    = set(path[1:]) if path else set()

    output: list[str] = []
    for ri, row in enumerate(maze):
        parts: list[str] = []
        for ci, cell in enumerate(row):
            coord = (ri, ci)
            if cell == 1 or coord in extra_walls:
                parts.append(f"{C_WALL}█{C_END}")
            elif coord == agent_pos:
                parts.append(f"{C_PATH}►{C_END}")
            elif coord == target_pos:
                parts.append(f"{C_TARGET}◆{C_END}")
            elif intercept is not None and coord == intercept and coord != target_pos:
                parts.append(f"{C_INTERCEPT}✦{C_END}")
            elif coord in path_set and cell not in {'S', 'E', '~'}:
                parts.append(f"{C_DOT}·{C_END}")
            elif cell in {'S', 'E'}:
                parts.append(f"{C_START}{cell}{C_END}")
            elif cell == '~':
                parts.append(f"{C_MUD}~{C_END}")
            else:
                parts.append(" ")
        output.append("".join(parts))

    legend_line = (
        f"  {C_PATH}►{C_END}=agent   "
        f"{C_TARGET}◆{C_END}=target   "
        f"{C_INTERCEPT}✦{C_END}=intercept   "
        f"{C_DOT}·{C_END}=planned path   "
        f"{C_WALL}▪{C_END}=dynamic wall"
    )
    _render_frame(legend_line, "\n".join(output), f"\n{message}")



# --- render_tsp() — TSP/Treasure Hunt render ---

def render_tsp(
    maze:    list[list[int | str]],
    message: str = "",
) -> None:
    """Single-pane render using TSP_CELL_RENDER (understands 'T', 'c', 'g' cells).

    Used for all TSP frames: segment walking, BF progress, GA overlays, final state.
    """
    output: list[str] = []
    for row in maze:
        output.append("".join(TSP_CELL_RENDER.get(cell, str(cell)) for cell in row))
    _render_frame("\n".join(output), f"\n{message}")



# --- render_tsp_ga_overlay() — GA live ghost-path ---

def render_tsp_ga_overlay(
    maze:        list[list[int | str]],
    path_matrix: list[list],
    chromosome:  list[int],
    gen:         int,
    total_gen:   int,
    best_cost:   float,
    prev_best:   float,
    pop_size:    int,
    stagnation:  int = 0,
    stag_limit:  int = 0,
) -> None:
    """Paint the current-best GA tour as a ghost overlay, then call render_tsp().

    Builds a display copy (never mutates the live maze), stamps inner path cells
    with 'g', builds an ANSI progress bar, and renders.
    """
    display = [row[:] for row in maze]
    current = 0
    for tidx in chromosome:
        path = path_matrix[current][tidx]
        if path:
            for r, c in path[1:-1]:  # skip start/end cells
                if display[r][c] not in {'S', 'E', 'T', 'c'}:
                    display[r][c] = 'g'
        current = tidx

    pct    = min(100, int(gen / max(total_gen, 1) * 100))
    filled = pct // 5
    bar    = f"{C_GA_LIVE}{'█' * filled}{C_END}{'░' * (PROGRESS_BAR_WIDTH - filled)}"

    delta_s = ""
    if prev_best > best_cost + _GA_IMPROVEMENT_THRESHOLD:
        delta_s = f"  {C_PATH}▼{int(prev_best - best_cost)} improved{C_END}"
    elif stag_limit > 0 and stagnation > stag_limit // 2:
        delta_s = f"  {C_DIM}↔ stagnating ({stagnation}/{stag_limit}){C_END}"

    stag_s = (
        f"  {C_DIM}Stagnation: {stagnation}/{stag_limit}{C_END}"
        if stag_limit > 0 else ""
    )
    message = (
        f"{C_GA_LIVE}🧬 Genetic Algorithm{C_END}  "
        f"Gen {gen:>4}/{total_gen}  [{bar}] {pct}%\n"
        f"   Best tour : {int(best_cost)} cells{delta_s}  "
        f"| Pop: {pop_size}{stag_s}"
    )
    render_tsp(display, message)
