"""
core/graph.py — distance calculations and path utilities.

Shared across all solver modules. No side effects.
"""
from __future__ import annotations


def manhattan_distance(p1: tuple[int, int], p2: tuple[int, int]) -> int:
    """Manhattan distance between two grid positions.

    Used as the A* / Greedy heuristic. Admissible on this grid because
    the minimum step cost is 1, so it never overestimates.
    """
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


# Short alias used in multi_agent_solver
manhattan = manhattan_distance


def _deduplicate_path(
    history: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Remove loops from a traversal history in O(n) time.

    When the agent visits a cell it's already been to, everything between
    the two visits is a loop — we cut it out. This repeats until there are
    no more loops, giving a physically walkable path with no teleportation.

    Example:
        history = [S, A, B, C, A, D, E]   # agent looped A → B → C → A
        result  = [S, A, D, E]             # loop B → C removed at re-entry of A

    Important: the naive "keep first occurrence" approach produces [S, A, B, C, D, E]
    which has a C→D teleportation gap (they're not adjacent). Loop-truncation is
    the correct fix.
    """
    path:     list[tuple[int, int]]       = []
    seen_idx: dict[tuple[int, int], int]  = {}

    for pos in history:
        if pos in seen_idx:
            idx = seen_idx[pos]
            # Remove everything after the first visit to this cell
            for removed in path[idx + 1:]:
                del seen_idx[removed]
            path = path[:idx + 1]
        else:
            seen_idx[pos] = len(path)
            path.append(pos)

    return path
