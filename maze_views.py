"""
maze_views.py — all the "show the user something" code for the pathfinding module.

Report card, tutorial, hypothesis challenge.
No session state lives here — it's all passed in from the controller.
"""
from __future__ import annotations
from core.types        import RunResult
from maze_genV4        import MazeStats
from ui.theme          import (
    C_HEAD, C_END, C_PATH, C_DIM, C_BIGO, C_PQ, C_RACE,
    C_HYP, C_START, C_STAT, C_BACK, C_MUD,
    ansi_enable_windows,
)
from ui.terminal_utils import _center_ansi, _term_width, _strip_ansi, clear_screen, flush_stdin
from algorithms.registry import (
    _REGISTRY,
    _STEP_LABELS, _ALGO_BIG_O, _ALGO_VERDICTS,
    _HOP_OPTIMAL, _COST_OPTIMAL, _MIGHT_FAIL,
)

ansi_enable_windows()

# ===========================================================================
# ── TOPOLOGY PANEL ─────────────────────────────────────────────────────────
# ===========================================================================
def show_topology_panel(
    stats:     MazeStats,
    generator: str = "dfs",
    rows:      int = 0,
    cols:      int = 0,
) -> None:
    """Show maze structure stats after generation, before the first run.

    Gives the user context about the maze before they pick an algorithm —
    dead end count, junctions, BFS path length, and a one-line hint about
    which algorithm families might struggle.
    """
    W = _term_width()

    # colour the score the same way the menu info bar does
    if stats.difficulty <= 25:
        dc = C_PATH
    elif stats.difficulty <= 50:
        dc = C_START
    elif stats.difficulty <= 75:
        dc = C_RACE
    else:
        dc = C_BACK

    band = (
        "easy"   if stats.difficulty <= 25 else
        "medium" if stats.difficulty <= 50 else
        "hard"   if stats.difficulty <= 75 else
        "brutal"
    )

    # one-line contextual hint
    if stats.dead_end_pct > 15:
        hint = "Many dead ends — wall followers will struggle here."
    elif stats.junction_pct > 15:
        hint = "Dense crossroads — uninformed search expands a lot."
    elif stats.bfs_path > 150:
        hint = "Long solution path — stochastic strategies will take a while."
    elif stats.difficulty <= 25:
        hint = "Open layout — most algorithms will solve this quickly."
    else:
        hint = f"BFS path is {stats.bfs_path} hops — {generator.upper()} topology."

    grid_pct = stats.passable * 100 // max(1, rows * cols)
    sep = "─" * W

    print("\n" + "═" * W)
    print(_center_ansi(
        f"🗺️   MAZE TOPOLOGY  |  {rows}×{cols}  |  {generator.upper()}"
        f"  |  {dc}{stats.difficulty}/100  {band}{C_END}",
        W,
    ))
    print("═" * W)
    print(f"  {'Passable cells':<24} {stats.passable:>5}   ({grid_pct}% of grid)")
    print(f"  {'Dead ends':<24} {stats.dead_ends:>5}   ({stats.dead_end_pct:.1f}% of passable)")
    print(f"  {'Junctions (3+ exits)':<24} {stats.junctions:>5}   ({stats.junction_pct:.1f}% of passable)")
    print(f"  {'Avg exits per cell':<24} {stats.avg_exits:>5.1f}")
    print(f"  {'Longest corridor':<24} {stats.longest_corridor:>5}   cells")
    print(f"  {'BFS path S→E':<24} {stats.bfs_path:>5}   hops")
    print(sep)
    print(f"  {C_DIM}💡 {hint}{C_END}")
    print("─" * W)
    flush_stdin()
    input(f"  Press {C_PATH}ENTER{C_END} to continue…")


# ===========================================================================
# ── REPORT CARD ───────────────────────────────────────────────────────────────
# ===========================================================================
def show_report_card(
    algo_name: str,
    result: RunResult,
    terrain_active: bool,
    maze_diff: int = -1,
) -> None:
    """Display a structured post-run statistics panel."""
    W          = _term_width()
    step_label = _STEP_LABELS.get(algo_name, "Nodes Expanded")
    verdict    = _ALGO_VERDICTS.get(algo_name, "")
    failed     = (result.steps == float('inf'))

    print("\n" + "═" * W)
    print(_center_ansi(f"📊  ALGORITHM REPORT CARD — {algo_name}", W))
    print("═" * W)

    if failed:
        print(
            f"  {C_HEAD}Result       : ❌  FAILED — algorithm could not reach the exit.{C_END}"
        )
        if algo_name in {"Wall Follower", "Left-Hand Rule"}:
            print(
                f"  {C_DIM}  └ Most likely cause: this maze has braided loops (complexity ≥ 5).\n"
                f"     Wall-following is only complete on simply-connected (perfect) mazes.\n"
                f"     Try Pledge (option 12) — it escapes island loops, or reduce complexity.{C_END}"
            )
        elif algo_name == "Pledge":
            print(
                f"  {C_DIM}  └ Pledge failed despite loop-escape logic — the maze may have\n"
                f"     extreme braiding or a layout that defeats the turn-counter heuristic.\n"
                f"     Use a graph-search algorithm (BFS/A*) for guaranteed completeness.{C_END}"
            )
        elif algo_name == "Random Mouse":
            print(
                f"  {C_DIM}  └ Random Mouse timed out — expected on large mazes.\n"
                f"     Expected steps to exit: O(V²). This is the expected result.{C_END}"
            )
        print(f"  Compute Time : {result.compute_time * 1000:.2f} ms")
    else:
        efficiency = (
            result.path_len / result.steps * 100 if result.steps > 0 else 0.0
        )
        print(f"  {step_label:<28}: {result.steps:.0f}")
        
        path_len_label = "Surviving Cells" if algo_name == "Dead-End Filling" else "Path Length"
        path_len_note  = "  (all unfilled cells — may include loop remnants)" if algo_name == "Dead-End Filling" else "  (interior cells — S and E not counted)"
        
        print(f"  {path_len_label:<28}: {result.path_len}{path_len_note}")

        if terrain_active:
            _cost_blind = algo_name not in _COST_OPTIMAL
            if _cost_blind:
                # BFS/Greedy/etc. count hops only — path_cost == path_len always.
                # Show the weighted cost of the path they found so the user can
                # compare it against Dijkstra's, but make the label unambiguous.
                print(
                    f"  {'Path Cost (hops only)':<28}: {result.path_cost}  "
                    f"{C_DIM}← terrain ignored during search — "
                    f"compare with Dijkstra to see the difference{C_END}"
                )
            else:
                print(f"  {'Path Cost (weighted)':<28}: {result.path_cost}  (road=1, mud=3)")
                if result.path_cost != result.path_len:
                    mud_cells = (result.path_cost - result.path_len) // 2
                    print(f"  {'  └ mud cells on path':<28}: {mud_cells}")

        if algo_name not in {"Dead-End Filling", "Wall Follower", "Pledge",
                             "Left-Hand Rule", "Bellman-Ford"}:
            ida_note = "  ← low by design: re-expansions trade nodes for O(d) memory" if algo_name == "IDA*" else ""
            print(
                f"  {'Search Efficiency':<28}: {efficiency:.1f}%"
                f"  (path ÷ {step_label.lower()}){ida_note}"
            )

        print(f"  {'Compute Time':<28}: {result.compute_time * 1000:.2f} ms  ⚠ single-run, interpreter noise ±1 ms")

    if maze_diff >= 0:
        _band = "easy" if maze_diff <= 25 else "medium" if maze_diff <= 50 else "hard" if maze_diff <= 75 else "brutal"
        print(f"  {'Maze Difficulty':<28}: {maze_diff}/100  ({_band})")

    # V6: always show Big-O in report card too
    bigo = _ALGO_BIG_O.get(algo_name, "")
    if bigo:
        print(f"  {C_BIGO}{'Complexity':<28}: {bigo}{C_END}")

    if verdict:
        print("─" * W)
        print(f"  💡 {verdict}")

    # Contextual low-complexity note for algorithms where branching matters
    if algo_name == "Bidirectional BFS" and not failed:
        if result.path_len > 0 and result.steps > result.path_len * 1.5:
            print(
                f"\n  {C_DIM}📐 Context: high node count relative to path length suggests\n"
                f"     a low-branching maze. Bidirectional BFS shines on open grids\n"
                f"     (complexity ≥ 4) where frontiers expand spherically.{C_END}"
            )
    print("═" * W)

def _family_tree_lines() -> list[str]:
    """Return the algorithm family tree as a list of strings, no printing.

    Kept separate so the pager can include it as a block without
    having to capture stdout.
    """
    D = C_DIM
    P = C_PATH
    S = C_START
    B = C_BIGO
    E = C_END

    return [
        f"  {B}Uninformed Search{E}",
        f"  {D}───────────────────────────────────────────────────────────────{E}",
        f"  {S}BFS{E}  {P}──► +terrain cost{E}  ──►  {S}Dijkstra{E}  {P}──► +heuristic{E}  ──►  {S}A*{E}",
        f"   │                                         {D}└─ heuristic only{E}  ──►  {S}Greedy Best-First{E}",
        f"   {P}└──► two frontiers{E}  ──────────────────────────────────────►  {S}Bidirectional BFS{E}",
        "",
        f"  {S}DFS{E}  {P}──► shuffle directions{E}  ────────────────────────────►  {S}Randomized DFS{E}",
        f"   {P}└──► iterative deepening + A* f-bound{E}  ────────────────────►  {S}IDA*{E}",
        "",
        f"  {B}Wall-Following{E}  {D}(O(1) space — no map, no memory){E}",
        f"  {D}───────────────────────────────────────────────────────────────{E}",
        f"  {S}Wall Follower{E}  {P}──► mirror{E}  ──────────────────────────────►  {S}Left-Hand Rule{E}",
        f"       {P}└──► +turn counter{E}  ────────────────────────────────►  {S}Pledge{E}  {D}(escapes islands){E}",
        "",
        f"  {B}Stochastic / Historical{E}",
        f"  {D}───────────────────────────────────────────────────────────────{E}",
        f"  {S}Random Mouse{E}  {P}──► +passage marking{E}  ────────────────────►  {S}Trémaux{E}  {D}(1882){E}",
        "",
        f"  {B}Topological{E}  {D}(not a search — solves by elimination){E}",
        f"  {D}───────────────────────────────────────────────────────────────{E}",
        f"  {S}Dead-End Filling{E}  {D}— seals cells with ≥3 wall neighbours one by one{E}",
        f"                       {D}what survives is the solution path{E}",
    ]


def _show_family_tree() -> None:
    """Print the family tree directly — used when called outside the pager."""
    _TW = _term_width()
    print("\n" + "─" * _TW)
    print(_center_ansi(f"{C_BIGO}🌳  ALGORITHM FAMILY TREE{C_END}", _TW))
    print(f"  {C_DIM}How the 15 algorithms relate to each other.{C_END}")
    print("─" * _TW + "\n")
    for line in _family_tree_lines():
        print(line)
    print()


# --- TUTORIAL ---

def show_tutorial() -> None:
    """Tutorial with block-aware pagination — no content ever scrolls off screen."""
    from ui.terminal_utils import _term_height

    _TW = _term_width()
    _TH = _term_height()

    # Minimum usable size. btop uses 80×24 as the de facto standard — we do the same.
    MIN_COLS, MIN_ROWS = 80, 24
    if _TW < MIN_COLS or _TH < MIN_ROWS:
        clear_screen()
        print(
            f"\n  ⚠️  Terminal too small for Tutorial\n"
            f"  Minimum : {MIN_COLS} columns × {MIN_ROWS} rows\n"
            f"  Current : {_TW} columns × {_TH} rows\n\n"
            f"  Resize your terminal and press ENTER to try again,\n"
            f"  or press Q to go back."
        )
        if input("\n  → ").strip().lower() != 'q':
            show_tutorial()
        return

    # Build content as blocks — each block stays together on one page.
    #
    # The bug that was here: tutorial_body strings contain embedded \n,
    # so treating each entry as a 2-element list made len(block) = 2
    # while A* for example actually prints 6 lines. The pager was then
    # fitting way more blocks per page than it should.
    # Fix: split each body on \n so len(block) == actual printed lines.
    blocks: list[list[str]] = []

    for s in _REGISTRY:
        body_parts = s.tutorial_body.split('\n')
        block      = [f"{C_START}{s.key}. {s.tutorial_title}:{C_END}"]
        # first body line needs the indent prefix;
        # continuation lines already have their spacing baked in
        block.append(f"   {body_parts[0]}")
        block.extend(body_parts[1:])
        blocks.append(block)

    # Family tree gets its own page (it's ~22 lines, needs breathing room)
    tree_header = [
        "─" * _TW,
        _center_ansi(f"{C_BIGO}🌳  ALGORITHM FAMILY TREE{C_END}", _TW),
        f"  {C_DIM}How the 15 algorithms relate to each other.{C_END}",
        "─" * _TW,
    ]
    blocks.append(tree_header + _family_tree_lines())

    footer_block = [
        f"  {C_BIGO}Big-O HUD is active during every algorithm run.{C_END}",
        f"  {C_PQ}PQ Inspector is active for A*, Dijkstra, and Greedy.{C_END}",
        f"  {C_RACE}Race Mode (option 20) runs any two algorithms side-by-side.{C_END}",
    ]
    blocks.append(footer_block)

    # Actual lines the header uses when rendered:
    #   print("\n" + "═" * _TW)  →  blank + ═══  = 2 lines
    #   print(title)              →  1 line
    #   print(legend + page)      →  1 line
    #   print("═" * _TW + "\n")  →  ═══ + blank  = 2 lines
    # Total header = 6.  Nav = ─── divider + input = 2.
    HEADER_H = 6
    NAV_H    = 2

    def _build_pages() -> list[list[list[str]]]:
        page_h   = max(4, _TH - HEADER_H - NAV_H)
        pages:   list[list[list[str]]] = []
        current: list[list[str]]       = []
        used                           = 0

        for block in blocks:
            needed = len(block) + 1  # +1 for the blank line after each block
            if used + needed > page_h and current:
                pages.append(current)
                current, used = [block], needed
            else:
                current.append(block)
                used += needed

        if current:
            pages.append(current)
        return pages

    pages = _build_pages()
    n     = len(pages)
    idx   = 0

    while True:
        clear_screen()
        print("\n" + "═" * _TW)
        print(_center_ansi("📚  ALGORITHM TUTORIAL & EXPLANATIONS  📚", _TW))
        print(
            f"  V = cells  |  d = depth  |  E = edges (~4V)"
            f"  {C_DIM}── page {idx + 1}/{n}{C_END}"
        )
        print("═" * _TW + "\n")

        for block in pages[idx]:
            for line in block:
                print(line)
            print()

        back = f"[b] back  " if idx > 0 else ""
        fwd  = f"[ENTER] next" if idx < n - 1 else f"[ENTER] done"
        print("─" * _TW)
        ans = input(f"  {back}{fwd}  [q] quit: ").strip().lower()

        if ans == 'q':
            break
        elif ans == 'b' and idx > 0:
            idx -= 1
        elif ans in {'', 'n'}:
            if idx < n - 1:
                idx += 1
            else:
                break

# ===========================================================================
# ── HYPOTHESIS CHALLENGE ──────────────────────────────────────────────────────
# ===========================================================================
def _hypothesis_pre_run(algo_name: str) -> dict[str, bool | int]:
    """Ask student to predict algorithm behaviour before the run starts."""
    print("\n" + "─" * 58)
    print(_center_ansi(f"{C_HYP}🔮  HYPOTHESIS — Predict {algo_name}'s behaviour{C_END}", 58))
    print("─" * 58)
    print(
        f"  {C_DIM}Scoring: Q1 (path found?) = 2 pts  "
        f"│  Q2 (hop-optimal?) = 1 pt  "
        f"│  Q3 (step estimate ±25%) = 1 pt{C_END}"
    )

    predictions: dict[str, bool | int] = {}

    if algo_name in _MIGHT_FAIL:
        while True:
            ans = input(
                f"  Q1. Will {algo_name} find a valid path? (y/n/skip): "
            ).strip().lower()
            if ans in {'y', 'yes', 'n', 'no', 's', 'skip', ''}:
                break
            print("  Please answer y, n, or skip.")
        if ans not in {'s', 'skip', ''}:
            predictions['finds_path'] = ans in {'y', 'yes'}
    else:
        print(f"  Q1. Will it find a path? — {C_PATH}Always YES{C_END} for {algo_name}.")

    if algo_name not in (_HOP_OPTIMAL | _COST_OPTIMAL):
        while True:
            ans = input(
                "  Q2. Will the path be hop-optimal (fewest cells)? (y/n/skip): "
            ).strip().lower()
            if ans in {'y', 'yes', 'n', 'no', 's', 'skip', ''}:
                break
            print("  Please answer y, n, or skip.")
        if ans not in {'s', 'skip', ''}:
            predictions['hop_optimal'] = ans in {'y', 'yes'}
    elif algo_name in _HOP_OPTIMAL:
        print(f"  Q2. Hop-optimal? — {C_PATH}Always YES{C_END} for {algo_name}.")
    else:
        print(
            f"  Q2. Hop-optimal? — {C_PATH}Cost-optimal YES{C_END}"
            f" (not necessarily fewest hops) for {algo_name}."
        )

    if algo_name != "Random Mouse":
        est_str = input(
            "  Q3. Estimate the step count — within 25% wins the point\n"
            "      (press ENTER to skip): "
        ).strip()
        if est_str.isdigit() and len(est_str) <= 10:
            predictions['step_estimate'] = int(est_str)

    print(f"  {C_HYP}✍️  Predictions locked in. Running algorithm…{C_END}\n")
    return predictions

def _hypothesis_post_run(
    predictions: dict,
    result: RunResult,
    algo_name: str,
) -> int:
    """Score the student's predictions. Returns points earned (max 4)."""
    earned = 0
    failed = result.steps == float('inf')
    W      = 58

    print("\n" + "─" * W)
    print(_center_ansi(f"{C_HYP}📋  HYPOTHESIS SCORECARD — {algo_name}{C_END}", W))
    print("─" * W)

    if 'finds_path' in predictions:
        predicted_found = predictions['finds_path']
        actually_found  = not failed
        if predicted_found == actually_found:
            print(
                f"  Path found?   Predicted: {'YES' if predicted_found else 'NO'}"
                f" → {C_PATH}✓ Correct! (+2 pts){C_END}"
            )
            earned += 2
        else:
            actual_str = 'FOUND' if actually_found else 'FAILED'
            print(
                f"  Path found?   Predicted: {'YES' if predicted_found else 'NO'}"
                f" → {C_HEAD}✗ Wrong (was {actual_str}){C_END}"
            )

    if 'hop_optimal' in predictions and not failed:
        predicted_opt = predictions['hop_optimal']
        actually_opt  = (algo_name in _HOP_OPTIMAL)
        if predicted_opt == actually_opt:
            print(
                f"  Hop-optimal?  Predicted: {'YES' if predicted_opt else 'NO'}"
                f" → {C_PATH}✓ Correct! (+1 pt){C_END}"
            )
            earned += 1
        else:
            print(
                f"  Hop-optimal?  Predicted: {'YES' if predicted_opt else 'NO'}"
                f" → {C_HEAD}✗ Wrong (actually {'YES' if actually_opt else 'NO'}){C_END}"
            )

    if 'step_estimate' in predictions and not failed:
        estimate  = predictions['step_estimate']
        actual    = result.steps if result.steps != float('inf') else 0
        threshold = max(1, int(actual * 0.25))

        if abs(estimate - actual) <= threshold:
            print(
                f"  Steps: {actual:<8} Estimate: {estimate}"
                f" → {C_PATH}✓ Within 25%! (+1 pt){C_END}"
            )
            earned += 1
        else:
            try:
                pct = abs(estimate - actual) / max(actual, 1) * 100
                pct_str = f"{pct:.0f}%"
            except OverflowError:
                pct_str = "astronomically off"
            print(
                f"  Steps: {actual:<8} Estimate: {estimate}"
                f" → {C_HEAD}✗ Off by {pct_str}{C_END}"
            )

    print("─" * W)
    return earned

# ===========================================================================
# ── STEP-BY-STEP EXPLAINER ────────────────────────────────────────────────────
# ===========================================================================

_PANEL_W: int = 46   # fixed panel width for side-by-side autopsy

# Algorithms whose explanation is "no deterministic logic to show".
# Shown identically at both levels.
_NO_LOGIC_ALGOS = {"random_mouse", "randomized_dfs"}

# Direction label helpers
_DIR_FULL  = {"N": "North", "E": "East", "S": "South", "W": "West"}
_DIR_ARROW = {"N": "↑", "E": "→", "S": "↓", "W": "←"}


def _panel_line(text: str = "", width: int = _PANEL_W) -> str:
    """Pad a line to fixed panel width (strip ANSI before measuring)."""
    visible = len(_strip_ansi(text))
    return text + " " * max(0, width - visible)


def _box(lines: list[str], width: int = _PANEL_W) -> list[str]:
    """Wrap lines in a light box border."""
    sep   = "─" * width
    inner = [_panel_line(f"  {l}", width) for l in lines]
    return [sep] + inner + [sep]


def show_step_explanation(
    algo_name:  str,
    extra:      "dict | None",
    step_num:   int,
    total:      int,
    level:      str,          # "beginner" | "advanced"
    maze_rows:  int = 0,
    maze_cols:  int = 0,
) -> list[str]:
    """Build the explainer panel for one autopsy step.

    Returns a list of strings (no trailing newline). Each string is already
    padded to _PANEL_W so the caller can zip them alongside maze rows.
    Extra=None means the recording predates the explainer — return a fallback.
    """
    P = _PANEL_W
    adv = (level == "advanced")

    def line(t=""):  return _panel_line(t, P)
    def sep():       return line("─" * P)
    def blank():     return line()

    # ── no extra data ─────────────────────────────────────────────────────────
    if extra is None:
        return [
            line(f"  {C_DIM}Step {step_num} / {total}  ·  {algo_name}{C_END}"),
            sep(),
            line(f"  {C_DIM}No explainer data for this recording."),
            line(f"  Run the algorithm again to enable"),
            line(f"  step-by-step explanations.{C_END}"),
            blank(),
        ]

    algo = extra.get("algo", "")

    # ── no-logic algorithms ───────────────────────────────────────────────────
    if extra.get("no_logic") or algo in _NO_LOGIC_ALGOS:
        return [
            line(f"  Step {step_num} / {total}  ·  {algo_name}"),
            sep(),
            line(f"  {C_DIM}This algorithm makes no"),
            line(f"  decisions — it picks a direction"),
            line(f"  at random each step."),
            blank(),
            line(f"  There is nothing to explain:{C_END}"),
            line(f"  {C_BACK}randomness has no reasoning.{C_END}"),
            blank(),
            line(f"  {C_DIM}Compare it to BFS or A* to see"),
            line(f"  what guided search looks like.{C_END}"),
        ]

    # ── BFS ───────────────────────────────────────────────────────────────────
    if algo == "bfs":
        d  = extra.get("dist", 0)
        q  = extra.get("queue_size", 0)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  BFS  {C_DIM}[FIFO queue]{C_END}"),
                sep(),
                line(f"  {C_BIGO}Distance from S:{C_END}  {d} hops"),
                line(f"  {C_BIGO}Queue:{C_END}           {q} cells pending"),
                blank(),
                line(f"  {C_DIM}BFS dequeues the oldest entry."),
                line(f"  All d={d} cells are exhausted"),
                line(f"  before any d={d+1} cell starts.{C_END}"),
                blank(),
                line(f"  {C_PATH}Guarantees min-hop path.{C_END}"),
                line(f"  {C_DIM}Cost-blind: mud = road.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  BFS"),
                sep(),
                line(f"  {C_DIM}This cell is {d} hops from the start.{C_END}"),
                blank(),
                line(f"  BFS explores like ripples in a"),
                line(f"  pond. Every cell {d} steps away"),
                line(f"  is visited before any cell"),
                line(f"  {d+1} steps away."),
                blank(),
                line(f"  {C_DIM}Queue: {q} cells still waiting.{C_END}"),
                blank(),
                line(f"  {C_PATH}Result: shortest path (in hops){C_END}"),
                line(f"  {C_DIM}but ignores terrain cost.{C_END}"),
            ]

    # ── DFS ───────────────────────────────────────────────────────────────────
    if algo == "dfs":
        st = extra.get("stack_size", 0)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  DFS  {C_DIM}[LIFO stack]{C_END}"),
                sep(),
                line(f"  {C_BIGO}Stack depth:{C_END}  {st} cells"),
                blank(),
                line(f"  {C_DIM}DFS pops the most recently added"),
                line(f"  cell (stack top). Goes deep before"),
                line(f"  it goes wide. Backtracks when"),
                line(f"  a dead end is hit.{C_END}"),
                blank(),
                line(f"  {C_BACK}Not guaranteed optimal.{C_END}"),
                line(f"  {C_DIM}Path quality depends on maze topology"),
                line(f"  and the order neighbours are added.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  DFS"),
                sep(),
                line(f"  {C_DIM}DFS always goes deeper before"),
                line(f"  it tries a different direction.{C_END}"),
                blank(),
                line(f"  Think of it as exploring one"),
                line(f"  corridor completely before"),
                line(f"  turning back to try another."),
                blank(),
                line(f"  Stack: {st} cells remembered."),
                blank(),
                line(f"  {C_BACK}May find a long path.{C_END}"),
                line(f"  {C_DIM}Compare to BFS to see the"),
                line(f"  difference in coverage.{C_END}"),
            ]

    # ── A* ────────────────────────────────────────────────────────────────────
    if algo == "astar":
        g   = extra.get("g", 0)
        h   = extra.get("h", 0)
        f   = extra.get("f", g + h)
        ops = extra.get("open_size", 0)
        cls = extra.get("closed_size", 0)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  A*  {C_DIM}[min-heap]{C_END}"),
                sep(),
                line(f"  {C_BIGO}g ={C_END} {g:<5}  path cost from S"),
                line(f"  {C_BIGO}h ={C_END} {h:<5}  Manhattan to E"),
                line(f"  {C_PATH}f ={C_END} {f:<5}  g+h  ← min in heap"),
                blank(),
                line(f"  {C_DIM}Open:   {ops} cells"),
                line(f"  Closed: {cls} cells{C_END}"),
                blank(),
                line(f"  {C_PATH}f = g+h chose this cell.{C_END}"),
                line(f"  {C_DIM}g stops costly detours."),
                line(f"  h guides toward the exit."),
                line(f"  Admissible h → optimal path.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  A*"),
                sep(),
                line(f"  A* picked this cell because it"),
                line(f"  had the best balance of:"),
                blank(),
                line(f"  {C_BIGO}Cost so far:{C_END}    {g}"),
                line(f"  {C_BIGO}Est. to exit:{C_END}   {h}"),
                line(f"  {C_PATH}Priority score:{C_END} {f}"),
                blank(),
                line(f"  Lower score = more promising."),
                line(f"  A* picks the lowest score"),
                line(f"  from all waiting cells."),
                blank(),
                line(f"  {C_PATH}Finds the optimal path.{C_END}"),
            ]

    # ── DIJKSTRA ──────────────────────────────────────────────────────────────
    if algo == "dijkstra":
        g   = extra.get("g", 0)
        ops = extra.get("open_size", 0)
        cls = extra.get("closed_size", 0)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  Dijkstra  {C_DIM}[min-heap]{C_END}"),
                sep(),
                line(f"  {C_BIGO}g = {g}{C_END}  cheapest cost from S"),
                line(f"  {C_DIM}h = 0  (no heuristic — A* with h=0){C_END}"),
                blank(),
                line(f"  {C_DIM}Open:   {ops}  ·  Closed: {cls}{C_END}"),
                blank(),
                line(f"  Expands radially by cost."),
                line(f"  {C_DIM}No heuristic means it explores"),
                line(f"  in all directions equally before"),
                line(f"  committing toward the exit.{C_END}"),
                blank(),
                line(f"  {C_PATH}Optimal on weighted graphs.{C_END}"),
                line(f"  {C_DIM}Slower than A* on open mazes.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  Dijkstra"),
                sep(),
                line(f"  Dijkstra always expands the"),
                line(f"  cheapest unvisited cell next."),
                blank(),
                line(f"  {C_BIGO}Cost to reach here:{C_END} {g}"),
                blank(),
                line(f"  Unlike A*, it has no sense"),
                line(f"  of direction. It explores"),
                line(f"  outward like a cost-weighted"),
                line(f"  ripple from the start."),
                blank(),
                line(f"  {C_PATH}Always finds the cheapest path.{C_END}"),
                line(f"  {C_DIM}Considers mud terrain cost.{C_END}"),
            ]

    # ── GREEDY BEST-FIRST ─────────────────────────────────────────────────────
    if algo == "greedy":
        h   = extra.get("h", 0)
        ops = extra.get("open_size", 0)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  Greedy B-F  {C_DIM}[min-heap]{C_END}"),
                sep(),
                line(f"  {C_BIGO}h = {h}{C_END}  Manhattan to E"),
                line(f"  {C_DIM}g ignored  (no path-cost tracking){C_END}"),
                blank(),
                line(f"  {C_DIM}Open: {ops} cells{C_END}"),
                blank(),
                line(f"  Picks the cell that looks"),
                line(f"  closest to the exit — ignores"),
                line(f"  how expensive the path was."),
                blank(),
                line(f"  {C_BACK}Not optimal.{C_END} Can be tricked"),
                line(f"  {C_DIM}by walls that look close but"),
                line(f"  require a long detour.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  Greedy Best-First"),
                sep(),
                line(f"  Greedy always moves toward"),
                line(f"  whatever cell looks closest"),
                line(f"  to the exit."),
                blank(),
                line(f"  {C_BIGO}Distance estimate to exit:{C_END} {h}"),
                blank(),
                line(f"  It never checks how expensive"),
                line(f"  the path was — only how"),
                line(f"  close it seems."),
                blank(),
                line(f"  {C_BACK}Can find bad paths{C_END} when a"),
                line(f"  {C_DIM}wall forces a long detour.{C_END}"),
            ]

    # ── BIDIRECTIONAL BFS ─────────────────────────────────────────────────────
    if algo == "bidirectional":
        fr = extra.get("frontier", "forward")
        arrow = "S →" if fr == "forward" else "← E"
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  Bidir. BFS"),
                sep(),
                line(f"  {C_BIGO}Active frontier:{C_END} {fr.upper()} ({arrow})"),
                blank(),
                line(f"  Two BFS waves run in parallel:"),
                line(f"  one from S, one from E."),
                line(f"  {C_DIM}When their frontiers meet,"),
                line(f"  the path is reconstructed"),
                line(f"  through the meeting point.{C_END}"),
                blank(),
                line(f"  {C_PATH}Visits ~half the nodes of BFS{C_END}"),
                line(f"  {C_DIM}on symmetric graphs.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  Bidirectional BFS"),
                sep(),
                line(f"  Currently expanding the"),
                line(f"  {C_BIGO}{fr.upper()} frontier {arrow}{C_END}"),
                blank(),
                line(f"  Two searches run at once:"),
                line(f"  one from S, one from E."),
                line(f"  They search toward each other"),
                line(f"  and meet in the middle."),
                blank(),
                line(f"  {C_PATH}Explores far fewer cells{C_END}"),
                line(f"  {C_DIM}than a single BFS sweep.{C_END}"),
            ]

    # ── WALL FOLLOWER / LEFT HAND ─────────────────────────────────────────────
    if algo in ("wall_follower", "left_hand"):
        hand  = "right" if algo == "wall_follower" else "left"
        d     = extra.get("direction", "?")
        dfull = _DIR_FULL.get(d, d)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  {hand.title()}-Hand Rule"),
                sep(),
                line(f"  {C_BIGO}Heading:{C_END} {dfull} {_DIR_ARROW.get(d,'?')}"),
                blank(),
                line(f"  Rule: always keep the {hand}"),
                line(f"  wall on your {hand} side."),
                line(f"  {C_DIM}1. Try to turn {hand}."),
                line(f"  2. If blocked, go straight."),
                line(f"  3. If blocked, turn {'right' if hand=='left' else 'left'}."),
                line(f"  4. If all blocked, turn back.{C_END}"),
                blank(),
                line(f"  {C_BACK}Fails on islands (detached walls).{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  {hand.title()}-Hand Rule"),
                sep(),
                line(f"  Heading: {dfull} {_DIR_ARROW.get(d,'?')}"),
                blank(),
                line(f"  The agent keeps its {hand} hand"),
                line(f"  touching a wall at all times."),
                blank(),
                line(f"  Works perfectly on mazes"),
                line(f"  where all walls connect to"),
                line(f"  the outer boundary."),
                blank(),
                line(f"  {C_BACK}Gets stuck on wall islands.{C_END}"),
            ]

    # ── PLEDGE ────────────────────────────────────────────────────────────────
    if algo == "pledge":
        d   = extra.get("direction", "?")
        tc  = extra.get("turn_count", 0)
        dfull = _DIR_FULL.get(d, d)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  Pledge"),
                sep(),
                line(f"  {C_BIGO}Heading:{C_END}     {dfull} {_DIR_ARROW.get(d,'?')}"),
                line(f"  {C_BIGO}Turn counter:{C_END} {tc}"),
                blank(),
                line(f"  {C_DIM}Pledge counts net turns from"),
                line(f"  the original direction."),
                line(f"  Leaves wall-following only when"),
                line(f"  counter returns to 0.{C_END}"),
                blank(),
                line(f"  {C_PATH}Solves mazes with islands.{C_END}"),
                line(f"  {C_DIM}Extends Wall Follower with"),
                line(f"  a turn-counting escape rule.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  Pledge Algorithm"),
                sep(),
                line(f"  Heading: {dfull}  Turn count: {tc}"),
                blank(),
                line(f"  Pledge is like Wall Follower"),
                line(f"  but smarter. It counts how"),
                line(f"  much it has turned."),
                blank(),
                line(f"  When the count hits 0 again"),
                line(f"  it knows it has escaped any"),
                line(f"  wall island it was following."),
                blank(),
                line(f"  {C_PATH}Works even on disconnected walls.{C_END}"),
            ]

    # ── DEAD-END FILLING ──────────────────────────────────────────────────────
    if algo == "dead_end":
        sealed = extra.get("sealed", 0)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  Dead-End Filling"),
                sep(),
                line(f"  {C_BIGO}Cells sealed so far:{C_END} {sealed}"),
                blank(),
                line(f"  {C_DIM}Identifies dead ends — cells with"),
                line(f"  exactly one open neighbour."),
                line(f"  Seals them, which may create"),
                line(f"  new dead ends further back."),
                line(f"  Repeats until only the solution"),
                line(f"  path remains unsealed.{C_END}"),
                blank(),
                line(f"  {C_PATH}Reveals solution by elimination.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  Dead-End Filling"),
                sep(),
                line(f"  {sealed} dead-end cells sealed so far."),
                blank(),
                line(f"  This algorithm fills in all"),
                line(f"  the dead ends — corridors"),
                line(f"  that lead nowhere."),
                blank(),
                line(f"  Once all dead ends are gone,"),
                line(f"  only the solution path is left."),
                blank(),
                line(f"  {C_PATH}Works backwards from dead ends.{C_END}"),
                line(f"  {C_DIM}No searching needed — just fill.{C_END}"),
            ]

    # ── IDA* ──────────────────────────────────────────────────────────────────
    if algo == "ida_star":
        depth = extra.get("depth", 0)
        bound = extra.get("bound", 0)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  IDA*"),
                sep(),
                line(f"  {C_BIGO}Current depth (g):{C_END} {depth}"),
                line(f"  {C_BIGO}Current bound:{C_END}    {bound}"),
                blank(),
                line(f"  {C_DIM}IDA* does DFS but stops any"),
                line(f"  branch where g+h exceeds"),
                line(f"  the current bound. When all"),
                line(f"  branches are cut, the bound"),
                line(f"  increases to the next f value.{C_END}"),
                blank(),
                line(f"  {C_PATH}Optimal. O(depth) memory.{C_END}"),
                line(f"  {C_DIM}Re-explores nodes — slower{C_END}"),
                line(f"  {C_DIM}than A* but uses almost no RAM.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  IDA*"),
                sep(),
                line(f"  Depth: {depth}   Bound: {bound}"),
                blank(),
                line(f"  IDA* is like A* but uses"),
                line(f"  almost no memory."),
                blank(),
                line(f"  It explores paths up to a cost"),
                line(f"  limit (the bound). If it"),
                line(f"  doesn't find the exit, it"),
                line(f"  raises the limit and tries again."),
                blank(),
                line(f"  {C_PATH}Finds the optimal path.{C_END}"),
                line(f"  {C_DIM}May revisit cells many times.{C_END}"),
            ]

    # ── BELLMAN-FORD ──────────────────────────────────────────────────────────
    if algo == "bellman_ford":
        rnd = extra.get("round", 0)
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  Bellman-Ford"),
                sep(),
                line(f"  {C_BIGO}Relaxation round:{C_END} {rnd}"),
                blank(),
                line(f"  {C_DIM}BF relaxes every edge in every"),
                line(f"  round. A cell's cost is updated"),
                line(f"  if a cheaper path is found."),
                line(f"  After V-1 rounds, all shortest"),
                line(f"  paths are guaranteed correct.{C_END}"),
                blank(),
                line(f"  {C_PATH}Handles negative weights.{C_END}"),
                line(f"  {C_DIM}O(V·E) — much slower than"),
                line(f"  Dijkstra or A* on mazes.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  Bellman-Ford"),
                sep(),
                line(f"  Round {rnd} of relaxation."),
                blank(),
                line(f"  Bellman-Ford checks every"),
                line(f"  path again and again, improving"),
                line(f"  its best known cost each round."),
                blank(),
                line(f"  It's very thorough — but also"),
                line(f"  very slow. You'll notice it"),
                line(f"  visits the same cells many times."),
                blank(),
                line(f"  {C_PATH}Always finds the shortest path.{C_END}"),
            ]

    # ── TRÉMAUX ───────────────────────────────────────────────────────────────
    if algo == "tremaux":
        marks = extra.get("marks_here", 0)
        marks_label = ["unvisited", "visited once", "visited twice"][min(marks, 2)]
        if adv:
            return [
                line(f"  Step {step_num}/{total}  ·  Trémaux (1882)"),
                sep(),
                line(f"  {C_BIGO}Marks at this cell:{C_END} {marks} ({marks_label})"),
                blank(),
                line(f"  {C_DIM}Rules:"),
                line(f"  • Unvisited passage → go in,"),
                line(f"    mark entry with 1 mark."),
                line(f"  • All passages marked once"),
                line(f"    → backtrack (mark entry twice)."),
                line(f"  • Never enter a passage marked"),
                line(f"    twice unless no choice.{C_END}"),
                blank(),
                line(f"  {C_PATH}Guarantees solution. Historically"),
                line(f"  {C_PATH}first provably correct maze alg.{C_END}"),
            ]
        else:
            return [
                line(f"  Step {step_num}/{total}  ·  Trémaux (1882)"),
                sep(),
                line(f"  This cell has been marked {marks} time(s)."),
                blank(),
                line(f"  Trémaux explores like a person"),
                line(f"  drawing chalk marks on the floor."),
                blank(),
                line(f"  Unvisited path → go in."),
                line(f"  All paths marked → backtrack."),
                line(f"  Never reuse a twice-marked path."),
                blank(),
                line(f"  {C_PATH}Always finds the exit.{C_END}"),
                line(f"  {C_DIM}The oldest known correct maze"),
                line(f"  algorithm — invented in 1882.{C_END}"),
            ]

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    return [
        line(f"  Step {step_num}/{total}  ·  {algo_name}"),
        sep(),
        line(f"  {C_DIM}No explainer registered for"),
        line(f"  algorithm key '{algo}'.{C_END}"),
        blank(),
    ]