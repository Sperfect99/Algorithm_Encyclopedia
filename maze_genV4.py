"""
maze_genV4.py — procedural maze generators.

Three algorithms, each with a different character:

  dfs      Hybrid DFS/Prim's. Long snaking corridors at low complexity,
           denser branching higher up. The default.

  kruskal  Randomised Kruskal's (edge-shuffle + union-find). Produces
           many short dead ends and lots of crossroads. Wall-following
           algorithms struggle here more than on DFS mazes.

  prim     Randomised Prim's. Grows outward from (0,0). Shorter corridors
           than DFS, more branchy than Kruskal's — somewhere in between.
"""
from __future__ import annotations

import random

_CELL_CHARS: dict[int | str, str] = {0: " ", 1: "█", '~': "~"}

MAZE_SIZES: dict[int, tuple[int, int]] = {
    0: (7,  15),  1: (9,  21),  2: (11,  27), 3: (15,  31),
    4: (19, 41),  5: (25, 51),  6: (31,  65), 7: (35,  81),
    8: (41, 101), 9: (51, 131), 10: (61, 151),
}

GENERATORS: dict[str, str] = {
    "dfs":     "DFS/Prim's  — long corridors, natural feel",
    "kruskal": "Kruskal's   — many crossroads, hard for wall-followers",
    "prim":    "Prim's      — grows from origin, medium density",
}
_GEN_CYCLE = ["dfs", "kruskal", "prim"]


def _generate_dfs(rows: int, cols: int, comp: int) -> list[list[int | str]]:
    """DFS/Prim's hybrid — original algorithm.

    branching_factor controls how often we pick a random stack entry instead
    of the top. 0.0 = pure DFS long corridors, ~0.9 = Prim's-like behaviour.
    """
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
            last_idx = len(stack) - 1
            if current_idx != last_idx:
                stack[current_idx] = stack[last_idx]
            stack.pop()

    return maze


def _generate_kruskal(rows: int, cols: int) -> list[list[int | str]]:
    """Randomised Kruskal's — builds a spanning tree by shuffling wall edges.

    Passage cells start isolated. Edges between adjacent cells are shuffled
    and accepted if they connect two different components (union-find).
    Result: perfect maze with many short dead ends and frequent crossroads.
    """
    maze = [[1] * cols for _ in range(rows)]
    cells = [(r, c) for r in range(0, rows, 2) for c in range(0, cols, 2)]
    for r, c in cells:
        maze[r][c] = 0

    parent = {cell: cell for cell in cells}

    def find(x: tuple) -> tuple:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: tuple, b: tuple) -> bool:
        pa, pb = find(a), find(b)
        if pa == pb:
            return False
        parent[pa] = pb
        return True

    edges = []
    for r, c in cells:
        if c + 2 < cols:
            edges.append(((r, c), (r, c + 2), (r, c + 1)))
        if r + 2 < rows:
            edges.append(((r, c), (r + 2, c), (r + 1, c)))

    random.shuffle(edges)
    for cell_a, cell_b, wall in edges:
        if union(cell_a, cell_b):
            maze[wall[0]][wall[1]] = 0

    return maze


def _generate_prim(rows: int, cols: int) -> list[list[int | str]]:
    """Randomised Prim's — grows outward from (0,0) picking a random frontier.

    Shorter corridors than DFS, more branching than Kruskal's.
    """
    maze = [[1] * cols for _ in range(rows)]
    maze[0][0] = 0
    in_maze: set[tuple[int, int]] = {(0, 0)}
    frontier: list[tuple[int, int, int, int]] = []

    def _add_frontier(r: int, c: int) -> None:
        for dr, dc in ((0, 2), (2, 0), (0, -2), (-2, 0)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in in_maze:
                frontier.append((nr, nc, r + dr // 2, c + dc // 2))

    _add_frontier(0, 0)

    while frontier:
        idx = random.randrange(len(frontier))
        nr, nc, wr, wc = frontier[idx]
        frontier[idx] = frontier[-1]
        frontier.pop()

        if (nr, nc) in in_maze:
            continue

        maze[nr][nc] = 0
        maze[wr][wc] = 0
        in_maze.add((nr, nc))
        _add_frontier(nr, nc)

    return maze


def generate_maze(
    complexity: int,
    generator:  str = "dfs",
) -> list[list[int | str]]:
    """Generate a maze at the given complexity level using the chosen algorithm.

    complexity  0-10 (clamped). Controls size via MAZE_SIZES.
    generator   "dfs" | "kruskal" | "prim" — defaults to dfs.
    """
    comp = max(0, min(10, int(complexity)))
    rows, cols = MAZE_SIZES[comp]
    gen = generator.lower().strip()

    if gen == "kruskal":
        maze = _generate_kruskal(rows, cols)
    elif gen == "prim":
        maze = _generate_prim(rows, cols)
    else:
        maze = _generate_dfs(rows, cols, comp)

    # Braiding only for DFS — Kruskal and Prim already vary naturally.
    if gen == "dfs" and comp >= 5:
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

    gen = input("Generator (dfs/kruskal/prim) [dfs]: ").strip() or "dfs"
    m   = generate_maze(level, gen)
    draw_maze(m)
    print(f"\n{gen} maze at complexity {level} ({len(m)}×{len(m[0])})")