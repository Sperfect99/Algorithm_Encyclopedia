"""
algorithms/tsp.py — TSP algorithm generators for the Treasure Hunt module.

Three algorithms for the Travelling Salesman variant on a maze grid:
    Nearest Neighbour  — greedy, always picks the closest unvisited treasure
    Brute Force        — exact optimal solution, only feasible for N <= 8
    Genetic Algorithm  — population-based search with crossover, mutation, and 2-opt polish

All three use a precomputed BFS path_matrix for maze-accurate distances
(not Euclidean), so the cost model reflects actual walkable terrain.
"""

from __future__ import annotations

import math
import time
import random
import itertools
from typing import Generator

from core.types import TreasureRunResult


# ---------------------------------------------------------------------------
# Private pure-math helpers
# These used to live inline in treasure_solver2.py. Moved here to keep
# the solver file clean — these are math only, no UI.
# ---------------------------------------------------------------------------

def _open_tour_cost(
    tour:        list[int],
    cost_matrix: list[list[float]],
) -> float:
    """Total weighted cost of visiting treasures in tour order, starting from S.

    Open path — agent stops at the last treasure, no return to S.
    Used by all three algorithms so the cost model stays consistent.
    """
    if not tour:
        return 0.0
    cost = cost_matrix[0][tour[0]]
    for k in range(len(tour) - 1):
        cost += cost_matrix[tour[k]][tour[k + 1]]
    return cost


def _tournament_select(
    population: list[list[int]],
    fitness_fn,
    k: int,
) -> list[int]:
    """Return the fittest individual from k randomly sampled competitors."""
    competitors = random.sample(population, min(k, len(population)))
    return min(competitors, key=fitness_fn)[:]


def _ox1_crossover(p1: list[int], p2: list[int]) -> list[int]:
    """OX1 crossover — copies a random slice from p1, fills the rest from p2 in order.

    Always produces a valid permutation.
    """
    n = len(p1)
    if n <= 1:
        return p1[:]

    a, b = sorted(random.sample(range(n), 2))
    child        = [-1] * n
    child[a:b+1] = p1[a:b+1]
    segment_set  = set(child[a:b+1])

    fill_vals = [x for x in p2 if x not in segment_set]
    fill_idx  = 0
    for i in range(n):
        if child[i] == -1:
            child[i] = fill_vals[fill_idx]
            fill_idx += 1

    return child


def _swap_mutate(chromosome: list[int]) -> list[int]:
    """Swap two random positions in the chromosome (O(1) valid mutation)."""
    c = chromosome[:]
    if len(c) < 2:
        return c
    i, j = random.sample(range(len(c)), 2)
    c[i], c[j] = c[j], c[i]
    return c


def _two_opt_improve(
    tour:        list[int],
    cost_matrix: list[list[float]],
) -> tuple[list[int], float]:
    """
    2-opt local search: repeatedly reverse sub-segments to eliminate crossing
    edges.  Stops when no improving swap exists (locally optimal).

    Uses '_open_tour_cost' — the single canonical cost function shared by
    all three TSP algorithms — so polishing always optimises the identical
    objective that the GA evolved under and that Brute Force enumerated.

    Returns (improved_tour, improved_total_cost).
    """
    best   = tour[:]
    best_c = _open_tour_cost(best, cost_matrix)
    N      = len(best)
    improved = True

    while improved:
        improved = False
        for i in range(N - 1):
            for j in range(i + 2, N):
                candidate = best[:i+1] + best[i+1:j+1][::-1] + best[j+1:]
                c = _open_tour_cost(candidate, cost_matrix)
                if c < best_c - 1e-9:
                    best, best_c = candidate, c
                    improved     = True
                    break
            if improved:
                break

    return best, best_c


def _tour_total_steps(
    tour_order:  list[int],
    path_matrix: list[list],
) -> float:
    """
    Compute the total walked steps for a tour by summing path segment lengths.

    Each segment path[i→j] contributes 'len(path) - 1' steps (the starting
    cell is not re-counted).  Returns 'float('inf')' if any segment is None
    (unreachable), matching the 'TreasureRunResult.total_steps: float' field.
    """
    steps   = 0
    current = 0
    for tidx in tour_order:
        path = path_matrix[current][tidx]
        if path is None:
            return float('inf')
        steps  += len(path) - 1
        current = tidx
    return steps


def _tour_time_to_first(
    tour_order:  list[int],
    path_matrix: list[list],
) -> int:
    """
    Steps walked before the first treasure is collected.
    Equals the length of the first BFS path minus 1.

    Returns 'int(float('inf'))' if the first treasure is unreachable
    (path is None), matching the sentinel convention used by
    '_tour_total_steps()'.  Previously returned 0, making an
    unreachable treasure indistinguishable from a start-adjacent one.
    """
    if not tour_order:
        return 0
    path = path_matrix[0][tour_order[0]]
    if path is None:
        return 999_999_999   # sentinel: unreachable (int, matches time_to_first: int)
    return len(path) - 1


# ===========================================================================
# ── ALGORITHM 1 — NEAREST NEIGHBOUR (GREEDY) ─────────────────────────────────
# ===========================================================================

def nearest_neighbour_gen(
    points:      list[tuple[int, int]],
    cost_matrix: list[list[float]],
    path_matrix: list[list],
) -> Generator[dict, None, None]:
    """
    Nearest Neighbour Greedy TSP generator.

    At each stop, greedily selects the unvisited treasure with the lowest
    weighted BFS cost (terrain-aware).  O(N) decisions; never backtracks.

    Pedagogical contrast:
    • Best Time-to-First: always rushes to the closest treasure.
    • Worst Total Tour: accumulated suboptimality from greedy myopia.

    Yields
    ------
    '"segment"'   — one path leg to animate (once per greedy choice)
    '"finalize"'  — signal to stamp all '.' cells as 'P'
    '"done"'      — complete TreasureRunResult
    """
    N         = len(points) - 1
    unvisited = set(range(1, N + 1))
    current   = 0
    tour_order: list[int] = []
    tour_cost   = 0
    compute     = 0.0

    while unvisited:
        # ── Pure greedy decision (timed) ──────────────────────────────────
        tc      = time.perf_counter()
        nearest = min(unvisited, key=lambda t: cost_matrix[current][t])
        compute += time.perf_counter() - tc

        path = path_matrix[current][nearest]
        if path is None:
            n_collected = N - len(unvisited)
            yield {
                "type":        "unreachable",
                "treasure_idx": nearest,
                "n_collected":  n_collected,
            }
            yield {
                "type":         "done",
                "result":       TreasureRunResult(
                    float('inf'), compute, 0, 0,
                    tuple(tour_order), n_collected, N,
                ),
            }
            return

        tour_cost += int(cost_matrix[current][nearest])
        tour_order.append(nearest)
        unvisited.discard(nearest)
        current = nearest

        yield {
            "type":           "segment",
            "path":           path,
            "collect_target": True,
            "algo_tag":       "nn",
            "meta": {
                "unvisited_remaining": len(unvisited),
            },
        }

    # ── Precompute final metrics from path lengths ─────────────────────────
    total_steps   = _tour_total_steps(tour_order, path_matrix)
    time_to_first = _tour_time_to_first(tour_order, path_matrix)

    yield {"type": "finalize"}
    yield {
        "type":   "done",
        "result": TreasureRunResult(
            total_steps, compute, tour_cost, time_to_first,
            tuple(tour_order), N, N,
        ),
    }


# ===========================================================================
# ── ALGORITHM 2 — BRUTE FORCE (EXACT OPTIMAL) ────────────────────────────────
# ===========================================================================

def brute_force_gen(
    points:      list[tuple[int, int]],
    cost_matrix: list[list[float]],
    path_matrix: list[list],
) -> Generator[dict, None, None]:
    """
    Brute Force Exact TSP generator.

    Enumerates all N! permutations and picks the minimum-cost tour.
    Mathematically guaranteed optimal.  Disabled for N > 8 (N! explosion).

    Pedagogical contrast:
    • A deliberate "think phase" (bf_progress yields) before any animation
      illustrates the cost of exact offline planning vs. online greedy.
    • Worst Time-to-First: may skip a nearby treasure to honour the optimal
      global route.

    Yields
    ------
    '"bf_disabled"'  — if N > 8, algorithm cannot run
    '"bf_progress"'  — ~50 progress-bar ticks during think phase
    '"bf_announce"'  — optimal tour found, driver should pause
    '"segment"'      — one path leg of the optimal tour to animate
    '"finalize"'     — signal to stamp '.' cells as 'P'
    '"done"'         — complete TreasureRunResult
    """
    N = len(points) - 1

    # ── Guard: N! is intractable for large N ──────────────────────────────
    if N > 8:
        n_fact = math.factorial(N)
        yield {
            "type":        "bf_disabled",
            "n_treasures": N,
            "n_fact":      n_fact,
        }
        yield {
            "type":   "done",
            "result": TreasureRunResult(float('inf'), 0.0, 0, 0, (), 0, N),
        }
        return

    treasure_idxs = list(range(1, N + 1))
    best_tour: list[int] = list(treasure_idxs)
    best_cost: float     = float('inf')
    n_perms    = math.factorial(N)
    progress_step = max(1, n_perms // 50)   # ~50 progress bar updates

    # ── Think phase: enumerate all N! permutations ────────────────────────
    t0 = time.perf_counter()

    for i, perm in enumerate(itertools.permutations(treasure_idxs)):
        c = _open_tour_cost(list(perm), cost_matrix)   # single canonical cost function
        if c < best_cost:
            best_cost = c
            best_tour = list(perm)

        if i % progress_step == 0:
            yield {
                "type":      "bf_progress",
                "checked":   i,
                "total":     n_perms,
                "best_cost": best_cost,
            }

    compute = time.perf_counter() - t0

    # ── Announce optimal tour before animation ────────────────────────────
    yield {
        "type":      "bf_announce",
        "best_tour": best_tour,
        "best_cost": best_cost,
        "compute":   compute,
    }

    # ── Animation phase: walk the optimal tour ────────────────────────────
    tour_cost = 0
    current   = 0

    for tidx in best_tour:
        path = path_matrix[current][tidx]
        if path is None:
            yield {
                "type":         "unreachable",
                "treasure_idx": tidx,
                "n_collected":  best_tour.index(tidx),
            }
            yield {
                "type":   "done",
                "result": TreasureRunResult(
                    float('inf'), compute, 0, 0, tuple(best_tour), 0, N,
                ),
            }
            return

        tour_cost += int(cost_matrix[current][tidx])
        current    = tidx

        yield {
            "type":           "segment",
            "path":           path,
            "collect_target": True,
            "algo_tag":       "bf",
            "meta": {
                "best_tour": best_tour,
                "best_cost": best_cost,
            },
        }

    # ── Precompute final metrics ───────────────────────────────────────────
    total_steps   = _tour_total_steps(best_tour, path_matrix)
    time_to_first = _tour_time_to_first(best_tour, path_matrix)

    yield {"type": "finalize"}
    yield {
        "type":   "done",
        "result": TreasureRunResult(
            total_steps, compute, tour_cost, time_to_first,
            tuple(best_tour), N, N,
        ),
    }


# ===========================================================================
# ── ALGORITHM 3 — GENETIC ALGORITHM (EVOLUTIONARY) ───────────────────────────
# ===========================================================================

def genetic_algorithm_gen(
    points:      list[tuple[int, int]],
    cost_matrix: list[list[float]],
    path_matrix: list[list],
) -> Generator[dict, None, None]:
    """
    Genetic Algorithm for grid TSP — pure generator.

    Evolves a population of tour orderings using:
      — Tournament selection  (pressure toward better solutions)
      — OX1 ordered crossover (preserves relative treasure-visit order)
      — Swap mutation         (escapes local minima stochastically)
      — Elitism (top-1)       (champion always survives intact)
      — 2-opt local polish    (post-convergence edge-swap refinement)

    The 'ga_overlay' yields (once per RENDER_EVERY generations) carry the
    current-best chromosome so the UI layer can paint a ghost-path overlay
    on the live maze — making the evolutionary process visually tangible.

    Pedagogical contrast:
    • Near-optimal Total Tour: outperforms Nearest Neighbour overall.
    • Moderate Time-to-First: between greedy and optimal depending on
      which chromosome wins the evolutionary race.

    Yields
    ------
    '"ga_overlay"'   — live ghost-path render frame (≤ 60 times total)
    '"ga_polishing"' — 2-opt phase started
    '"ga_announce"'  — convergence summary, driver should pause
    '"segment"'      — one path leg of the evolved tour to animate
    '"finalize"'     — signal to stamp '.' cells as 'P'
    '"done"'         — complete TreasureRunResult
    """
    N = len(points) - 1

    # ── Trivial case: single treasure ─────────────────────────────────────
    if N < 2:
        path = path_matrix[0][1] if N == 1 else None
        if N == 0 or path is None:
            yield {
                "type":   "done",
                "result": TreasureRunResult(float('inf'), 0.0, 0, 0, (), 0, N),
            }
            return

        cost          = int(cost_matrix[0][1])
        total_steps   = len(path) - 1
        time_to_first = total_steps

        yield {
            "type":           "segment",
            "path":           path,
            "collect_target": True,
            "algo_tag":       "ga",
            "meta":           {"trivial": True},
        }
        yield {"type": "finalize"}
        yield {
            "type":   "done",
            "result": TreasureRunResult(
                total_steps, 0.0, cost, time_to_first, (1,), 1, N,
            ),
        }
        return

    # ── Hyperparameters (scale with N) ────────────────────────────────────
    POP_SIZE         = max(40, N * 20)
    GENERATIONS      = max(120, N * 55)
    MUT_RATE         = 0.18
    TOURN_K          = max(2, min(5, POP_SIZE // 12))
    STAGNATION_LIMIT = max(25, GENERATIONS // 6)
    RENDER_EVERY     = max(1, GENERATIONS // 60)   # ≤ 60 visual overlay frames

    treasure_idxs = list(range(1, N + 1))

    # Fitness: open-path tour cost via the shared canonical function.
    # Using _open_tour_cost guarantees the GA, Brute Force, and 2-opt
    # polishing all optimise the exact same objective function.
    def fitness(chrom: list[int]) -> float:
        return _open_tour_cost(chrom, cost_matrix)

    # ── Initialise population ─────────────────────────────────────────────
    population = [random.sample(treasure_idxs, N) for _ in range(POP_SIZE)]

    best_ever  = min(population, key=fitness)
    best_cost  = fitness(best_ever)
    prev_best  = best_cost * 1.5   # sentinel: ensures first frame shows delta
    stagnation = 0
    final_gen  = GENERATIONS
    t0         = time.perf_counter()

    # ── Evolution loop ────────────────────────────────────────────────────
    for gen in range(1, GENERATIONS + 1):

        # Elitism: carry forward the champion unchanged.
        new_pop: list[list[int]] = [best_ever[:]]

        while len(new_pop) < POP_SIZE:
            p1    = _tournament_select(population, fitness, TOURN_K)
            p2    = _tournament_select(population, fitness, TOURN_K)
            child = _ox1_crossover(p1, p2)
            if random.random() < MUT_RATE:
                child = _swap_mutate(child)
            new_pop.append(child)

        population = new_pop

        # Track improvement.
        current_best = min(population, key=fitness)
        current_cost = fitness(current_best)

        if current_cost < best_cost - 1e-9:
            prev_best  = best_cost
            best_cost  = current_cost
            best_ever  = current_best[:]
            stagnation = 0
        else:
            stagnation += 1

        # ── Live overlay render frame ──────────────────────────────────────
        if gen % RENDER_EVERY == 0 or gen == 1:
            yield {
                "type":       "ga_overlay",
                "chromosome": best_ever[:],
                "gen":        gen,
                "total_gen":  GENERATIONS,
                "best_cost":  best_cost,
                "prev_best":  prev_best,
                "pop_size":   POP_SIZE,
                "stagnation": stagnation,
                "stag_limit": STAGNATION_LIMIT,
            }
            prev_best = best_cost   # reset delta display for next frame

        # Early convergence.
        if stagnation >= STAGNATION_LIMIT:
            final_gen = gen
            break

    # ── 2-opt local polish ────────────────────────────────────────────────
    pre_polish_cost = best_cost
    yield {
        "type":            "ga_polishing",
        "pre_polish_cost": pre_polish_cost,
    }

    polished, polished_cost = _two_opt_improve(best_ever, cost_matrix)
    improvement = best_cost - polished_cost
    best_ever   = polished
    best_cost   = polished_cost

    compute = time.perf_counter() - t0

    # ── Announce convergence before animation ─────────────────────────────
    yield {
        "type":        "ga_announce",
        "final_gen":   final_gen,
        "total_gen":   GENERATIONS,
        "best_cost":   best_cost,
        "compute":     compute,
        "best_tour":   best_ever,
        "improvement": improvement,
    }

    # ── Animate the evolved optimal tour ──────────────────────────────────
    tour_cost = 0
    current   = 0

    for tidx in best_ever:
        path = path_matrix[current][tidx]
        if path is None:
            yield {
                "type":         "unreachable",
                "treasure_idx": tidx,
                "n_collected":  best_ever.index(tidx),
            }
            yield {
                "type":   "done",
                "result": TreasureRunResult(
                    float('inf'), compute, 0, 0, tuple(best_ever), 0, N,
                ),
            }
            return

        tour_cost += int(cost_matrix[current][tidx])
        current    = tidx

        yield {
            "type":           "segment",
            "path":           path,
            "collect_target": True,
            "algo_tag":       "ga",
            "meta":           {"best_tour": best_ever},
        }

    # ── Precompute final metrics ───────────────────────────────────────────
    total_steps   = _tour_total_steps(best_ever, path_matrix)
    time_to_first = _tour_time_to_first(best_ever, path_matrix)

    yield {"type": "finalize"}
    yield {
        "type":   "done",
        "result": TreasureRunResult(
            total_steps, compute, tour_cost, time_to_first,
            tuple(best_ever), N, N,
        ),
    }
