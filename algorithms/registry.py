"""
algorithms/registry.py — metadata for all 15 pathfinding algorithms.

Display names, Big-O strings, verdicts, and tutorial content all live here.
To add a new algorithm: drop a solve() file in algorithms/pathfinding/ and
add one AlgorithmSpec entry to _REGISTRY. That's it.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field as _field


@dataclass
class AlgorithmSpec:
    # ── Identity ──────────────────────────────────────────────────────────
    key:           str    # menu choice string ("1"..."15")
    module_name:   str    # importable name under algorithms.pathfinding
    display_name:  str    # shown in every UI surface
    bench_name:    str    # short label for benchmark table columns

    # ── Menu display ──────────────────────────────────────────────────────
    section:       str    # groups algorithms under section headers
    menu_note:     str    # parenthetical after the display name

    # ── Educational metadata ──────────────────────────────────────────────
    big_o:          str   # complexity string for the Big-O HUD
    verdict:        str   # post-run pedagogical note shown in report card
    tutorial_title: str   # heading in the tutorial
    tutorial_body:  str   # body text in the tutorial

    # ── Customisable labels ───────────────────────────────────────────────
    step_label:    str  = "Nodes Expanded"

    # ── Hypothesis Challenge classification ───────────────────────────────
    hop_optimal:   bool = False
    cost_optimal:  bool = False
    might_fail:    bool = False

    # ── UI badges ────────────────────────────────────────────────────────
    pq_inspector:  bool = False   # show [PQ✦] badge in menu and tutorial

    # ── Large-maze advisory ───────────────────────────────────────────────
    slow_maze_warning: bool = False
    slow_warn_cells:   int  = 2_500

    # ── Benchmark opt-in ─────────────────────────────────────────────────
    bench_slow_warn:   bool = False
    bench_warn_cells:  int  = 0       # 0 = always prompt; >0 = only if maze exceeds this
    bench_warn_reason: str  = ""


_REGISTRY: list[AlgorithmSpec] = [
    # ── Classic Search ────────────────────────────────────────────────────
    AlgorithmSpec(
        key="1", module_name="bfs", display_name="BFS",
        bench_name="BFS", section="Classic Search",
        menu_note="hop-optimal",
        big_o="T:O(V+E)       S:O(V)  ▸ deque FIFO",
        verdict=(
            "BFS guarantees the fewest-hop path by exploring in concentric waves.\n"
            "   On weighted terrain it counts hops, not cost — so its path may be\n"
            "   more expensive (terrain-wise) than Dijkstra's or A*'s."
        ),
        tutorial_title="BFS (Breadth-First Search)",
        tutorial_body=(
            "collections.deque (FIFO)  |  space O(V)\n"
            "   Explores in concentric waves; guarantees fewest HOPS but is\n"
            "   cost-blind. On weighted terrain its path may cost more than\n"
            "   Dijkstra's or A*'s."
        ),
        hop_optimal=True,
    ),
    AlgorithmSpec(
        key="2", module_name="dfs", display_name="DFS",
        bench_name="DFS", section="Classic Search",
        menu_note="depth-first, non-optimal",
        big_o="T:O(V+E)       S:O(V)  ▸ list LIFO",
        verdict=(
            "DFS finds a path, not the best path. It plunges deep before\n"
            "   backtracking, ignoring all cost and alternatives. Highly memory-\n"
            "   efficient but the resulting path is often far from optimal."
        ),
        tutorial_title="DFS (Depth-First Search)",
        tutorial_body=(
            "list (LIFO Stack)  |  space O(V)\n"
            "   Plunges deep before backtracking. Memory-efficient; yields\n"
            "   non-optimal, cost-blind paths. Foundation of Trémaux & IDA*."
        ),
    ),
    AlgorithmSpec(
        key="3", module_name="astar", display_name="A*",
        bench_name="A*", section="Classic Search",
        menu_note="cost + heuristic, optimal ★",
        big_o="T:O((V+E)logV) S:O(V)  ▸ heapq  f = g(cost) + h(manhattan)",
        verdict=(
            "A* is cost-aware: g(n) accumulates terrain cost (mud = 3) and\n"
            "   h(n) estimates distance to goal, so it routes around mud when\n"
            "   a cheaper road detour exists. Compare path cost to BFS and Greedy."
        ),
        tutorial_title="A* Search  ★ cost-aware + heuristic",
        tutorial_body=(
            "heapq (Priority Queue)  |  space O(V)\n"
            "   f = g(n) + h(n). g accumulates terrain cost; h = Manhattan.\n"
            "   Routes around mud AND focuses toward the goal.\n"
            "   h = Manhattan is admissible (min step cost = 1, so h ≤ true cost).\n"
            "   V6: PQ Inspector shows top-3 heap entries live during animation."
        ),
        cost_optimal=True, pq_inspector=True,
    ),
    AlgorithmSpec(
        key="4", module_name="greedy", display_name="Greedy Best-First",
        bench_name="Greedy BFS", section="Classic Search",
        menu_note="heuristic only, cost-blind",
        big_o="T:O((V+E)logV) S:O(V)  ▸ heapq  f = h only  (cost-blind!)",
        verdict=(
            "Greedy ignores accumulated cost entirely — it blindly chases the\n"
            "   heuristic. On weighted terrain it charges through mud because it\n"
            "   has no g(n). Compare its path cost to A* and Dijkstra."
        ),
        tutorial_title="Greedy Best-First Search",
        tutorial_body=(
            "heapq (Priority Queue)  |  space O(V)\n"
            "   f = h(n) only — ignores cost. Charges through mud obliviously.\n"
            "   Compare path cost to A* with the Duel overlay.\n"
            "   V6: PQ Inspector shows top-3 heap entries live during animation."
        ),
        pq_inspector=True,
    ),
    AlgorithmSpec(
        key="5", module_name="dijkstra", display_name="Dijkstra",
        bench_name="Dijkstra", section="Classic Search",
        menu_note="uniform cost, radial, optimal ★",
        big_o="T:O((V+E)logV) S:O(V)  ▸ heapq  f = g only  (A* with h=0)",
        verdict=(
            "Dijkstra is A* without a heuristic (h = 0). It explores radially\n"
            "   outward from start, always expanding the cheapest known node.\n"
            "   Cost-aware: routes around mud. Compare its explored region to A*'s\n"
            "   — Dijkstra expands in all directions; A* focuses toward the goal."
        ),
        tutorial_title="Dijkstra's Algorithm  ★ cost-aware",
        tutorial_body=(
            "heapq (Priority Queue)  |  space O(V)\n"
            "   f = g(n) only — A* with h = 0. Explores radially, cost-aware.\n"
            "   Routes around mud. Slower than A* because it lacks direction."
        ),
        cost_optimal=True, pq_inspector=True,
    ),
    AlgorithmSpec(
        key="6", module_name="bidirectional", display_name="Bidirectional BFS",
        bench_name="Bi-BFS", section="Classic Search",
        menu_note="two frontiers, meet in middle",
        big_o="T:O(b^(d/2))   S:O(b^(d/2)) ▸ two deques  (b=branch, d=depth)",
        verdict=(
            "Two BFS waves expand from start and end simultaneously.\n"
            "   Best case: explores ~√ as many cells as single-source BFS.\n"
            "   Path length may occasionally differ from plain BFS by 1-2 hops\n"
            "   due to the candidate-tracking approach at meeting depth."
        ),
        tutorial_title="Bidirectional BFS",
        tutorial_body=(
            "two deque (FIFO)  |  space O(b^(d/2))\n"
            "   Two BFS waves meet in the middle. Saves cells explored vs BFS.\n"
            "   Cost-blind: hop count only. Compare to BFS with Race/Duel mode."
        ),
        hop_optimal=False,
    ),
    AlgorithmSpec(
        key="7", module_name="ida_star", display_name="IDA*",
        bench_name="IDA*", section="Memory-Constrained",
        menu_note="O(depth) space, iterative deepening",
        big_o="T:O(b^d) worst S:O(d)  ▸ DFS stack  (re-expands each iteration)",
        verdict=(
            "IDA* uses O(d) space instead of A*'s O(V) — the trade-off is\n"
            "   re-expanding nodes each iteration. Steps look inflated compared\n"
            "   to A*; that's by design, not inefficiency. Heatmaps show why."
        ),
        tutorial_title="IDA* (Iterative Deepening A*)",
        tutorial_body=(
            "DFS Stack  |  space O(d)\n"
            "   A* with O(depth) memory. Re-expands nodes across iterations.\n"
            "   High step count is the price of low memory. Compare to A*."
        ),
        cost_optimal=True,
        slow_maze_warning=True, slow_warn_cells=2_500,
    ),
    AlgorithmSpec(
        key="8", module_name="bellman_ford", display_name="Bellman-Ford",
        bench_name="Bellman-Ford", section="Memory-Constrained",
        menu_note="edge-relaxation, O(V·E)",
        big_o="T:O(V·E)       S:O(V)  ▸ edge list  (relaxes ALL edges each pass)",
        verdict=(
            "Bellman-Ford relaxes every edge in the graph each pass — O(V·E)\n"
            "   compared to Dijkstra's O((V+E)logV). Correct on any non-negative\n"
            "   weights. Pedagogically important: see the wavefront expand pass by pass."
        ),
        tutorial_title="Bellman-Ford",
        tutorial_body=(
            "edge list  |  space O(V)\n"
            "   Relaxes all edges every pass until no improvement. Slower than\n"
            "   Dijkstra but handles any non-negative weights correctly."
        ),
        step_label="Relaxations",
        cost_optimal=True,
        slow_maze_warning=True, slow_warn_cells=2_500,
    ),
    AlgorithmSpec(
        key="9", module_name="dead_end_filling", display_name="Dead-End Filling",
        bench_name="Dead-End Fill", section="Topology-Based",
        menu_note="seals dead ends, reveals solution",
        big_o="T:O(V)         S:O(V)  ▸ deque  (topological, not navigational)",
        verdict=(
            "Not a search — a topological operation. Seals cells with ≥3 wall\n"
            "   neighbours iteratively. What remains IS the solution. Works\n"
            "   perfectly on simple mazes; leaves loop remnants on braided ones."
        ),
        tutorial_title="Dead-End Filling",
        tutorial_body=(
            "deque (FIFO)  |  space O(V)\n"
            "   Seals dead ends iteratively. Doesn't navigate — reveals the solution\n"
            "   by elimination. Produces loop remnants on braided (complexity ≥ 5) mazes."
        ),
        step_label="Walls Collapsed",
    ),
    AlgorithmSpec(
        key="10", module_name="wall_follower", display_name="Wall Follower",
        bench_name="Wall Follower", section="Wall-Following",
        menu_note="right-hand rule",
        big_o="T:O(V)         S:O(1)  ▸ state machine  (memoryless)",
        verdict=(
            "Wall Follower is O(1) space: it only knows current position and\n"
            "   heading. No cost model — mud is identical to road. Fails on\n"
            "   braided mazes with disconnected interior wall islands."
        ),
        tutorial_title="Wall Follower (Right-Hand Rule)",
        tutorial_body=(
            "Variables (State)  |  space O(1)\n"
            "   Keep the RIGHT hand on the wall. No memory, no cost model.\n"
            "   Fails on mazes with disconnected interior wall islands."
        ),
        step_label="Steps Walked", might_fail=True,
    ),
    AlgorithmSpec(
        key="11", module_name="left_hand", display_name="Left-Hand Rule",
        bench_name="Left-Hand Rule", section="Wall-Following",
        menu_note="left-hand mirror",
        big_o="T:O(V)         S:O(1)  ▸ state machine  (mirror of right)",
        verdict=(
            "The left-hand twin of Wall Follower: keeps its left hand on the wall\n"
            "   instead of its right. Same O(1) memory, same failure modes on\n"
            "   braided mazes. Produces mirror-image paths to Wall Follower,\n"
            "   demonstrating that 'left' and 'right' are architecturally equivalent."
        ),
        tutorial_title="Left-Hand Rule  ★ mirror",
        tutorial_body=(
            "Variables (State)  |  space O(1)\n"
            "   Left-hand mirror of Wall Follower. Same failure modes; may\n"
            "   produce completely different routes on asymmetric mazes."
        ),
        step_label="Steps Walked", might_fail=True,
    ),
    AlgorithmSpec(
        key="12", module_name="pledge", display_name="Pledge",
        bench_name="Pledge", section="Wall-Following",
        menu_note="escapes islands",
        big_o="T:O(V)         S:O(1)  ▸ state + turn-counter  (O(1)!)",
        verdict=(
            "Pledge adds one cumulative turn integer to Wall Follower. Still O(1).\n"
            "   The counter detects island-induced loops and forces detachment,\n"
            "   solving cases where plain Wall Follower circles forever."
        ),
        tutorial_title="Pledge Algorithm",
        tutorial_body=(
            "Variables (State + Counter)  |  space O(1)\n"
            "   Adds ONE cumulative turn integer to Wall Follower. Detects\n"
            "   island loops and forces detachment. Still O(1)."
        ),
        step_label="Steps Walked", might_fail=True,
    ),
    AlgorithmSpec(
        key="13", module_name="random_mouse", display_name="Random Mouse",
        bench_name="Random Mouse", section="Stochastic / Historical",
        menu_note="pure chaos, O(1)",
        big_o="T:O(V²) expected S:O(1) ▸ none  (cover time theorem; worst-case unbounded)",
        verdict=(
            "Zero heuristic, zero memory, zero cost model. Each step is fully\n"
            "   independent. Expected cover time: O(V²) by the random walk cover\n"
            "   time theorem — a 61×151 maze expects ~340 million steps to fully\n"
            "   explore. Exists to demonstrate why any intelligence dominates\n"
            "   pure stochastic search. Worst-case: unbounded."
        ),
        tutorial_title="Random Mouse (Drunkard's Walk)",
        tutorial_body=(
            "None  |  space O(1)\n"
            "   Random direction each step — no memory, no heuristic, no cost.\n"
            "   Capped at 10 000 steps. Why any intelligence beats randomness."
        ),
        step_label="Steps Wandered", might_fail=True,
        bench_slow_warn=True, bench_warn_cells=0,
        bench_warn_reason="can take up to 10 000 steps",
    ),
    AlgorithmSpec(
        key="14", module_name="randomized_dfs", display_name="Randomized DFS",
        bench_name="Rand DFS", section="Stochastic / Historical",
        menu_note="shuffled DFS, stochastic",
        big_o="T:O(V+E)       S:O(V)  ▸ shuffled LIFO  (deterministic→stochastic)",
        verdict=(
            "Standard DFS with DIRECTIONS shuffled at every expansion. Retains all\n"
            "   DFS guarantees (finds a path if one exists, LIFO, same space) but\n"
            "   produces jagged, unpredictable paths each run. Demonstrates how\n"
            "   randomness transforms a deterministic algorithm into a stochastic one."
        ),
        tutorial_title="Randomized DFS  ★ stochastic",
        tutorial_body=(
            "list (LIFO Stack)  |  space O(V)\n"
            "   DFS with DIRECTIONS shuffled every expansion. Same correctness\n"
            "   guarantees; different path each run. Determinism → stochastic."
        ),
    ),
    AlgorithmSpec(
        key="15", module_name="tremaux", display_name="Trémaux",
        bench_name="Trémaux", section="Stochastic / Historical",
        menu_note="chalk marks, 1882",
        big_o="T:O(V)         S:O(V)  ▸ set + stack  (1882 chalk method)",
        verdict=(
            "Trémaux's 1882 chalk-mark method is complete on any connected maze:\n"
            "   it provably finds a path or proves none exists. O(V) memory.\n"
            "   Magenta '×' marks show permanently abandoned passages.\n"
            "   Implementation note: capped at V×4 steps as a safety bound —\n"
            "   on valid mazes this cap is never reached in practice."
        ),
        tutorial_title="Trémaux's Algorithm (Chalk Method)",
        tutorial_body=(
            "set (Visited) + Stack  |  space O(V)\n"
            "   1882 method. Marks (.) and double-marks (×) passages.\n"
            "   Guarantees solution. × cells = permanently abandoned."
        ),
        step_label="Steps Traced", might_fail=True,
    ),
]


# --- DERIVED VIEWS ---

_ALGO_NAMES:  dict[str, str]           = {s.key: s.display_name for s in _REGISTRY}
_STEP_LABELS: dict[str, str]           = {
    s.display_name: s.step_label
    for s in _REGISTRY
    if s.step_label != "Nodes Expanded"
}
_SPEC_BY_KEY: dict[str, AlgorithmSpec] = {s.key: s for s in _REGISTRY}

_MENU_SECTIONS: dict[str, list[AlgorithmSpec]] = {}
for _s in _REGISTRY:
    _MENU_SECTIONS.setdefault(_s.section, []).append(_s)


def _get_generator(module_name: str):
    """Import solve() from the given module under algorithms.pathfinding on first use."""
    mod = importlib.import_module(f"algorithms.pathfinding.{module_name}")
    return mod.solve


_ALGO_BIG_O:    dict[str, str] = {s.display_name: s.big_o    for s in _REGISTRY}
_ALGO_VERDICTS: dict[str, str] = {s.display_name: s.verdict  for s in _REGISTRY}

_HOP_OPTIMAL:  frozenset[str] = frozenset({"BFS"})
_COST_OPTIMAL: frozenset[str] = frozenset({"A*", "Dijkstra", "Bellman-Ford"})
_MIGHT_FAIL:   frozenset[str] = frozenset({
    "Wall Follower", "Left-Hand Rule", "Pledge", "Random Mouse", "Trémaux",
})
