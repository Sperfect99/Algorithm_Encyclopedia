"""
maze_views.py — all the "show the user something" code for the pathfinding module.

Report card, tutorial, hypothesis challenge.
No session state lives here — it's all passed in from the controller.
"""
from __future__ import annotations
from core.types        import RunResult
from ui.theme          import (
    C_HEAD, C_END, C_PATH, C_DIM, C_BIGO, C_PQ, C_RACE,
    C_HYP, C_START, C_STAT,
    ansi_enable_windows,
)
from ui.terminal_utils import _center_ansi, _term_width, clear_screen
from algorithms.registry import (
    _REGISTRY,
    _STEP_LABELS, _ALGO_BIG_O, _ALGO_VERDICTS,
    _HOP_OPTIMAL, _COST_OPTIMAL, _MIGHT_FAIL,
)

ansi_enable_windows()

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
        print(f"  {step_label:<28}: {int(result.steps)}")
        
        path_len_label = "Surviving Cells" if algo_name == "Dead-End Filling" else "Path Length"
        path_len_note  = "  (all unfilled cells — may include loop remnants)" if algo_name == "Dead-End Filling" else "  (interior cells — S and E not counted)"
        
        print(f"  {path_len_label:<28}: {result.path_len}{path_len_note}")

        if terrain_active:
            _cost_blind = algo_name not in _COST_OPTIMAL
            _cost_note = (
                f"  {C_DIM}← cost-blind: terrain ignored during search{C_END}"
                if _cost_blind else ""
            )
            print(f"  {'Path Cost (weighted)':<28}: {result.path_cost}  (road=1, mud=3){_cost_note}")
            
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
        actual    = int(result.steps)
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