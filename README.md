<div align="center">

# 🧩 Algorithm Encyclopedia

### Watch algorithms solve mazes in real-time — pure Python, zero dependencies.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active%20Development-orange?style=flat-square)]()
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey?style=flat-square)]()
[![Algorithms](https://img.shields.io/badge/Algorithms-24%2B-purple?style=flat-square)]()

</div>

---

## What is this?

Pick an algorithm. Watch it think. Compare it to another.

Reading about BFS and A\* is one thing. Watching BFS fan out in every direction while A\* cuts straight toward the goal — on the same maze, at the same time — is something else entirely. That's what this project is for.

It's a terminal visualizer for 24+ classic algorithms across four problem domains, built without any external libraries. Every algorithm runs step-by-step with live colour animation, a live Big-O HUD, and a post-run report card. You can replay any run frame by frame, overlay two paths on the same maze, or race two algorithms side by side. The focus throughout is on making the *behaviour* of each algorithm visible, not just its output.

---

## Demo

```
⚔️  DUEL: BFS  vs  A*

S█~  █ █   █*****█   █   █   █
*█ ███ █ █ █*█ █*███~█ ███ ███~
***█    ~█ █*█ █*****█   █   ~~
 █*█ ███████*███~███*█ ███████~
~█*    █   █*█ █ █***  █  *****
██*███████ █*█ ███*█ █████*███*
  ***********  █***█   █  *█  *
 █ █~███████████*█████████*█ █*
 █ █~  █   █~  █***  █*****█ █*
 ███~███ ███ █████*███*███████*
 █       █  ~█ █ █***█*█  *****
 █████ ███ ███ █ ███*█*███*████
     █   █ █       █*█*  █*█
████ ███ █ ███ █ █ █*█*███*███
       █       █ █ █***  █****E

──────────────────────────────────────────────────────────────
  Metric                 BFS                A*
──────────────────────────────────────────────────────────────
  Steps                  250                238
  Path Length            91                 91
  Path Cost              107                107
  Compute Time           1.92 ms           0.36 ms
──────────────────────────────────────────────────────────────
  1=BFS only (0)   2=A* only (0)   *=shared (91)
──────────────────────────────────────────────────────────────
```

## Modules

| # | Module | Algorithms |
|---|--------|-----------|
| **1** | [Classic Pathfinding](#classic-pathfinding) | BFS, DFS, A\*, Dijkstra, IDA\*, Bellman-Ford, Bidirectional BFS, Greedy, Wall Followers, Pledge, Random Mouse, Trémaux |
| **2** | [TSP / Treasure Hunt](#tsp--treasure-hunt) | Nearest Neighbour, Brute Force (exact, N≤8), Genetic Algorithm + 2-opt |
| **3** | [MAPF](#multi-agent-pathfinding-mapf) | Independent A\*, Prioritised Planning, Conflict-Based Search (CBS) |
| **4** | [Pursuit-Evasion](#pursuit-evasion) | Naive Recalculation, Dynamic Repair (D\* Lite inspired), Greedy Intercept |

---

## Algorithms

### Classic Pathfinding

15 algorithms on procedurally generated mazes (7×15 up to 61×151). Weighted terrain — mud patches cost 3× to traverse — makes the difference between cost-aware and cost-blind algorithms immediately visible. Run BFS and Dijkstra on the same muddy maze and compare the paths.

| Algorithm | Optimal? | Cost-Aware? | Space | Notes |
|-----------|:--------:|:-----------:|-------|-------|
| BFS | ✅ hops | ❌ | O(V) | Fewest hops, ignores terrain cost |
| DFS | ❌ | ❌ | O(V) | Memory-efficient, path quality suffers |
| A\* | ✅ cost | ✅ | O(V) | f = g(cost) + h(manhattan) |
| Dijkstra | ✅ cost | ✅ | O(V) | A\* with h = 0 — expands radially |
| Greedy Best-First | ❌ | ❌ | O(V) | f = h only. Charges through mud |
| Bidirectional BFS | ≈ hops | ❌ | O(V) | Two frontiers from S and E |
| IDA\* | ✅ cost | ✅ | O(d) | A\* memory at the cost of re-expansions |
| Bellman-Ford | ✅ cost | ✅ | O(V) | Relaxes all edges per pass, O(V·E) |
| Dead-End Filling | — | — | O(V) | Topological: seals dead ends, reveals path |
| Wall Follower | ❌ | ❌ | O(1) | Right-hand rule — fails on braided mazes |
| Left-Hand Rule | ❌ | ❌ | O(1) | Mirror of Wall Follower |
| Pledge | ❌ | ❌ | O(1) | Wall follower + turn counter to escape islands |
| Random Mouse | ❌ | ❌ | O(1) | Pure random walk. Capped at 10k steps |
| Randomized DFS | ❌ | ❌ | O(V) | DFS with shuffled direction order |
| Trémaux (1882) | ✅ | ❌ | O(V) | Original chalk-mark method. Complete |

### TSP / Treasure Hunt

Collect all N treasure points on a live maze grid in optimal order. Distances are BFS-accurate — no straight-line shortcuts. The Genetic Algorithm animates each generation live, showing crossover and mutation happening in real time.

| Algorithm | Optimal? | Notes |
|-----------|:--------:|-------|
| Nearest Neighbour | ❌ | Greedy. Always fast, often good enough |
| Brute Force | ✅ | Exact optimal. Only enabled for N ≤ 8 (N! grows fast) |
| Genetic Algorithm | ≈ | Crossover + mutation + 2-opt polish. Animated generation by generation |

### Multi-Agent Pathfinding (MAPF)

Route 2–3 agents to individual goals without vertex collisions. The three strategies represent a real trade-off: Independent A\* is fast but produces conflicts; CBS is optimal but searches exponentially. Conflicts are highlighted live during simulation.

| Algorithm | Conflict-Free? | Optimal? | Notes |
|-----------|:--------------:|:--------:|-------|
| Independent A\* | ❌ | per agent | Plans in isolation. Conflicts shown live |
| Prioritised Planning | ✅ | suboptimal | Reserves space-time cells — fast, no backtracking |
| CBS | ✅ | ✅ SoC | Constraint tree search. Planning phase animated |

### Pursuit-Evasion

One agent chases a target that actively flees. The target moves every tick. The key comparison is replan frequency — Naive replans every single step, Dynamic Repair only when the path breaks. Watch the difference in behaviour.

| Strategy | Replan Frequency | Notes |
|----------|:----------------:|-------|
| Naive Recalculation | Every tick | Correct but expensive |
| Dynamic Repair | On path invalidation | Repairs the existing path when blocked |
| Greedy Intercept | On path invalidation | Predicts target trajectory and cuts it off |

---

## Features

**Live visualisation**
- Step-by-step animation with adjustable speed: Slow (150ms) / Normal (50ms) / Fast / Instant
- Big-O HUD — time and space complexity shown on screen during every run
- Priority Queue Inspector — live top-3 heap entries for A\*, Dijkstra, Greedy (lets you see what the algorithm is "thinking")
- Fog of War — hides unvisited cells so you only see the search frontier expanding

**Comparison tools**
- **Algorithm Duel** — two paths overlaid on the same maze; shared cells, A-only cells, and B-only cells each get a distinct colour
- **Race Mode** — split-screen simultaneous replay of two algorithms on identical mazes
- **Benchmark** — all 15 algorithms timed on the same maze, sorted results table

**Post-run analysis**
- **Autopsy** — step-by-step forward/backward replay of any run (ENTER / b / jump to step N)
- **Heatmap** — 256-colour exploration map with absolute visit-count tiers; the same colour always means the same visit count, so you can compare heatmaps across different algorithms
- **Report Card** — steps, compute time, path length, terrain cost, efficiency ratio, and a short explanation of the result

**Classroom / learning tools**
- **Hypothesis Challenge** — before each run, predict the algorithm's behaviour; your predictions are scored afterward and tracked across the session
- **Tutorial** — data structure and complexity notes for each algorithm, accessible from the main menu
- Weighted terrain (mud = 3×) makes cost-aware vs cost-blind behaviour visible without any explanation needed

---

## Requirements

- **Python 3.9+**
- A terminal with ANSI colour support:
  - Linux / macOS — any modern terminal works out of the box
  - Windows — **Windows Terminal** or VS Code's integrated terminal. cmd.exe won't work.
- Minimum terminal size: **80 columns × 30 rows**
- Race Mode requires **~120+ columns** (two mazes side by side)
- No pip installs. No virtual environment. Standard library only.

---

## Getting started

```bash
git clone https://github.com/Sperfect99/Algorithm_Encyclopedia.git
cd Algorithm_Encyclopedia
python _encyclopedia_launcher.py
```

Or run a single module directly:

```bash
python maze_controller.py      # Classic Pathfinding (15 algorithms)
python treasure_solver2.py     # TSP / Treasure Hunt
python multi_agent_solver.py   # MAPF
python dynamic_solver3.py      # Pursuit-Evasion
```

**First run:** pick complexity **3 or 4**, speed **Normal**, no terrain. Start with BFS (option 1) and A\* (option 3) — run both on the same maze and then use **Duel** (option d after each run) to overlay the two paths. That single comparison shows more than an hour of reading.

---

## Project structure

```
algorithm-encyclopedia/
│
├── _encyclopedia_launcher.py     # master menu — start here
│
├── maze_controller.py            # Classic Pathfinding session loop
├── maze_views.py                 # report card, tutorial, hypothesis UI
├── maze_modes.py                 # autopsy, duel, race, benchmark
├── maze_genV4.py                 # procedural maze generation (hybrid DFS/Prim's)
│
├── treasure_solver2.py           # TSP / Treasure Hunt module
├── treasure_gen.py               # maze + treasure placement + BFS distance matrix
│
├── multi_agent_solver.py         # MAPF module
├── mapf.py                       # CBS, Independent A*, Prioritised Planning generators
│
├── dynamic_solver3.py            # Pursuit-Evasion module
├── dynamic_gen3.py               # dynamic environment + target movement
├── pursuit.py                    # pursuit strategy generators
├── tsp.py                        # TSP algorithm generators
│
├── algorithms/
│   ├── registry.py               # metadata for all 15 pathfinding algorithms
│   └── pathfinding/              # one file per algorithm — bfs.py, astar.py, …
│
├── core/
│   ├── types.py                  # RunResult, MapfResult, PursuitResult, etc.
│   ├── grid.py                   # DIRECTIONS, PASSABLE, terrain_cost()
│   └── graph.py                  # manhattan_distance(), _deduplicate_path()
│
└── ui/
    ├── theme.py                  # all ANSI colour constants
    ├── terminal_utils.py         # cursor control, precise_sleep, ANSI stripping
    ├── renderer.py               # render(), render_split(), render_heatmap(), …
    └── animation.py              # generator drivers — connects algorithms to the terminal
```

Generators in `algorithms/` have no UI code — they just yield state. The `ui/` layer drives them and handles all rendering. This means you can run any algorithm headlessly (no terminal needed) by consuming the generator directly.

---

## Status

The core visualiser is **complete and stable**. Active development continues.

**Complete**
- All 15 pathfinding algorithms — animation, autopsy, heatmap, duel, race, benchmark
- TSP module — Nearest Neighbour, Brute Force, and Genetic Algorithm (with 2-opt)
- MAPF module — Independent A\*, Prioritised Planning, and CBS
- Pursuit-Evasion module — all three strategies
- MVC refactoring — `core/`, `ui/`, `algorithms/` package structure in place

**Planned**

*Core / stability*
- [ ] Smoke tests for each algorithm on known mazes
- [ ] Config file — save preferred speed, complexity, and terrain between sessions
- [ ] Graceful degradation when terminal is too small (currently a hard warning)
- [ ] Windows column-width review for Race Mode on cmd/PowerShell

*Analysis & data*
- [x] **Benchmark CSV export** — after a benchmark run, optionally save results to `benchmark_results.csv` so you can open them in Excel/Python/Sheets and build your own charts
- [ ] **Multi-run statistics** — run each algorithm N times across different mazes and report mean/min/max; a single benchmark is random, 20 runs give a statistically meaningful picture
- [x] **ASCII bar chart** — visual step-count comparison directly in the terminal after Benchmark, using block characters, no external libraries

*New algorithms*
- [ ] **Bidirectional A\*** — the cost-aware version of the Bidirectional BFS already in the suite
- [ ] Additional maze generators — Kruskal's and Prim's alongside the existing DFS hybrid (different structural properties, worth comparing)
- [ ] MAPF: support more than 3 agents

*Extensibility*
- [ ] **Custom algorithm plugin system** — a `custom/` folder with a minimal `solve()` template; drop a file in, add one entry to the registry, and it appears in the menu automatically. The architecture already supports this — just needs the folder convention and a documented template
- [x] **Maze import/export** — save a specific maze to disk and reload it later; currently every maze is randomly generated and lost when you exit
- [ ] **Run replay from file** — save a full Autopsy recording as JSON and load it in a later session; currently recordings are lost on exit

*Visualisation*
- [ ] **Algorithm family tree** — a static diagram in the Tutorial showing how the algorithms relate to each other (BFS → Dijkstra → A\*, DFS → IDA\*, Wall Follower → Pledge, etc.)
- [ ] Pursuit: dynamic wall perturbation as a toggleable mode

---

## License

MIT — see [LICENSE](LICENSE)
