"""
maze_genV4.py — procedural maze generator.

Hybrid DFS / Prim's. Low complexity → long snaking corridors.
High complexity → dense branches, dead ends, and loops.
Complexity >= 5 punches extra holes in walls to create braiding.
"""
from __future__ import annotations

import random

_CELL_CHARS: dict[int | str, str] = {0: " ", 1: "█", '~': "~"}

MAZE_SIZES: dict[int, tuple[int, int]] = {
    0: (7,  15),  1: (9,  21),  2: (11,  27), 3: (15,  31),
    4: (19, 41),  5: (25, 51),  6: (31,  65), 7: (35,  81),
    8: (41, 101), 9: (51, 131), 10: (61, 151),
}


def generate_maze(complexity: int) -> list[list[int | str]]:
    """Generate a maze at the given complexity level (0-10).

    1 = wall, 0 = open, 'S' = start, 'E' = end.
    """
    comp = max(0, min(10, int(complexity)))
    rows, cols = MAZE_SIZES[comp]

    # branching_factor controls the DFS vs Prim's mix.
    # 0.0 → pure DFS (long corridors), ~0.9 → Prim's-style (many dead ends)
    # Divided by 11 not 10 so the max is ~0.909, never fully random.
    branching_factor: float = comp / 11.0

    maze: list[list[int | str]] = [[1] * cols for _ in range(rows)]
    stack: list[tuple[int, int]] = [(0, 0)]
    maze[0][0] = 0

    while stack:
        if random.random() < branching_factor:
            current_idx = random.randint(0, len(stack) - 1)
        else:
            current_idx = len(stack) - 1

        r, c = stack[current_idx]
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        random.shuffle(directions)

        moved = False
        for dr, dc in directions:
            nr, nc = r + dr * 2, c + dc * 2
            if 0 <= nr < rows and 0 <= nc < cols and maze[nr][nc] == 1:
                maze[r + dr][c + dc] = 0
                maze[nr][nc] = 0
                stack.append((nr, nc))
                moved = True
                break

        if not moved:
            # Swap-and-pop: O(1) removal instead of O(N) list shift.
            # On a complexity-10 maze the stack can hold thousands of entries,
            # so this matters — without it generation becomes O(V^2).
            last_idx = len(stack) - 1
            if current_idx != last_idx:
                stack[current_idx] = stack[last_idx]
            stack.pop()

    # Braiding: punch holes in walls to create loops at higher complexities.
    # Only connects cells that were already corridor-adjacent (not random walls),
    # so the result looks natural rather than like random missing blocks.
    if comp >= 5:
        holes_to_punch = (comp * rows * cols) // 100
        for _ in range(holes_to_punch):
            rr = random.randint(1, rows - 2)
            cc = random.randint(1, cols - 2)

            if maze[rr][cc] == 1:
                vertical_corridor = (
                    maze[rr - 1][cc] == 0 and maze[rr + 1][cc] == 0
                    and maze[rr][cc - 1] == 1 and maze[rr][cc + 1] == 1
                )
                horizontal_corridor = (
                    maze[rr][cc - 1] == 0 and maze[rr][cc + 1] == 0
                    and maze[rr - 1][cc] == 1 and maze[rr + 1][cc] == 1
                )
                if vertical_corridor or horizontal_corridor:
                    maze[rr][cc] = 0

    maze[0][0] = 'S'
    maze[rows - 1][cols - 1] = 'E'
    return maze


def add_terrain(
    maze: list[list[int | str]],
    density: float = 0.12,
) -> list[list[int | str]]:
    """Scatter mud patches on an existing maze in-place.

    Seeds a handful of cells and spreads to neighbours probabilistically
    so clusters look natural rather than uniformly random.
    S and E are never converted.
    """
    rows, cols = len(maze), len(maze[0])
    open_cells = [
        (r, c) for r in range(rows) for c in range(cols)
        if maze[r][c] == 0
    ]
    if not open_cells:
        return maze

    n_seeds = max(1, int(len(open_cells) * density / 3))
    seeds = random.sample(open_cells, min(n_seeds, len(open_cells)))

    for sr, sc in seeds:
        for dr, dc in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)):
            nr, nc = sr + dr, sc + dc
            if (
                0 <= nr < rows and 0 <= nc < cols
                and maze[nr][nc] == 0
                and random.random() < 0.7
            ):
                maze[nr][nc] = '~'

    return maze


def draw_maze(maze: list[list[int | str]]) -> None:
    """Quick debug print. The solver uses its own ANSI renderer."""
    for row in maze:
        print("".join(_CELL_CHARS.get(cell, str(cell)) for cell in row))


if __name__ == "__main__":
    try:
        level = int(input("Complexity level (0-10): "))
    except ValueError:
        level = 3

    m = generate_maze(level)
    draw_maze(m)
    print(f"\nGenerated maze at complexity {level} ({len(m)}x{len(m[0])})")
