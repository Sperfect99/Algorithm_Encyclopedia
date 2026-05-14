"""
_encyclopedia_launcher.py — master menu for the Algorithm Encyclopedia.

Launches the four modules on demand. Each one is imported only when selected
so startup is instant. A missing file prints a warning and falls back to the
menu rather than crashing everything.
"""

from __future__ import annotations

import os
import sys
import time

from ui.theme import *  # noqa: F401,F403
from ui.terminal_utils import (
    _strip_ansi, _center_ansi, _term_height, _term_width,
    clear_screen as _clear_screen,
)

ansi_enable_windows()

# modules that crashed during this session — consulted at exit for CI exit code
_CHILD_CRASHED: set[str] = set()


# --- banner ---

_BANNER = rf"""
{C_GOLD}╔════════════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                                ║
║  {C_TITLE}{C_BOLD}  ████████╗██╗  ██╗███████╗                                                                   {C_GOLD}║
║  {C_TITLE}  ╚══██╔══╝██║  ██║██╔════╝                                                                   {C_GOLD}║
║  {C_TITLE}     ██║   ███████║█████╗                                                                     {C_GOLD}║
║  {C_TITLE}     ██║   ██╔══██║██╔══╝                                                                     {C_GOLD}║
║  {C_TITLE}     ██║   ██║  ██║███████╗                                                                   {C_GOLD}║
║  {C_TITLE}     ╚═╝   ╚═╝  ╚═╝╚══════╝                                                                   {C_GOLD}║
║  {C_PATH}{C_BOLD}    █████╗ ██╗      ██████╗  ██████╗ ██████╗ ██╗████████╗██╗  ██╗███╗  ███╗                   {C_GOLD}║
║  {C_PATH}   ██╔══██╗██║     ██╔════╝ ██╔═══██╗██╔══██╗██║╚══██╔══╝██║  ██║████╗████║                   {C_GOLD}║
║  {C_PATH}   ███████║██║     ██║  ███╗██║   ██║██████╔╝██║   ██║   ███████║██╔████╔██║                  {C_GOLD}║
║  {C_PATH}   ██╔══██║██║     ██║   ██║██║   ██║██╔══██╗██║   ██║   ██╔══██║██║╚██╔╝██║                  {C_GOLD}║
║  {C_PATH}   ██║  ██║███████╗╚██████╔╝╚██████╔╝██║  ██║██║   ██║   ██║  ██║██║ ╚═╝ ██║                  {C_GOLD}║
║  {C_PATH}   ╚═╝  ╚═╝╚══════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝   ╚═╝   ╚═╝  ╚═╝╚═╝     ╚═╝                  {C_GOLD}║
║  {C_EMBER}{C_BOLD}  ███████╗███╗   ██╗ ██████╗██╗   ██╗ ██████╗██╗      ██████╗                                 {C_GOLD}║
║  {C_EMBER}  ██╔════╝████╗  ██║██╔════╝╚██╗ ██╔╝██╔════╝██║     ██╔═══██╗                                {C_GOLD}║
║  {C_EMBER}  █████╗  ██╔██╗ ██║██║      ╚████╔╝ ██║     ██║     ██║   ██║                                {C_GOLD}║
║  {C_EMBER}  ██╔══╝  ██║╚██╗██║██║       ╚██╔╝  ██║     ██║     ██║   ██║                                {C_GOLD}║
║  {C_EMBER}  ███████╗██║ ╚████║╚██████╗   ██║   ╚██████╗███████╗╚██████╔╝                                {C_GOLD}║
║  {C_EMBER}  ╚══════╝╚═╝  ╚═══╝ ╚═════╝   ╚═╝    ╚═════╝╚══════╝ ╚═════╝                                 {C_GOLD}║
║  {C_BIGO}{C_BOLD}  ██████╗ ███████╗██████╗ ██╗ █████╗                                                          {C_GOLD}║
║  {C_BIGO}  ██╔══██╗██╔════╝██╔══██╗██║██╔══██╗                                                         {C_GOLD}║
║  {C_BIGO}  ██████╔╝█████╗  ██████╔╝██║███████║                                                         {C_GOLD}║
║  {C_BIGO}  ██╔═══╝ ██╔══╝  ██║  ██║██║██╔══██║                                                         {C_GOLD}║
║  {C_BIGO}  ██║     ███████╗██████╔╝██║██║  ██║                                                         {C_GOLD}║
║  {C_BIGO}  ╚═╝     ╚══════╝╚═════╝ ╚═╝╚═╝  ╚═╝                                                         {C_GOLD}║
║                                                                                                ║
║  {C_DIM}A Terminal-Based Suite of Pathfinding & Optimization Visualizers{C_END}                              {C_GOLD}║
║  {C_DIM}Standard Library Only  ·  Python 3.9+  ·  Zero Dependencies{C_END}                                   {C_GOLD}║
║                                                                                                ║
╚════════════════════════════════════════════════════════════════════════════════════════════════╝{C_END}
"""

_BANNER_HEIGHT:       int = 33
_MENU_BODY_HEIGHT:    int = 31
_FULL_DISPLAY_HEIGHT: int = _BANNER_HEIGHT + _MENU_BODY_HEIGHT

_COMPACT_HEADER: str = (
    f"{C_GOLD}★  {C_TITLE}{C_BOLD}THE ALGORITHM ENCYCLOPEDIA{C_END}"
    f"{C_GOLD}  ·  {C_DIM}Python 3.9+  ·  Zero Dependencies{C_END}"
    f"{C_GOLD}  ★{C_END}"
)


# --- module registry ---

_MODULES: list[tuple[str, str, str, str]] = [
    (
        "1",
        "maze_controller",
        "Classic Pathfinding",
        (
            f"    {C_BIGO}15 algorithms{C_END} on procedurally generated mazes.\n"
            f"    BFS · DFS · A* · Dijkstra · IDA* · Bellman-Ford · Wall Followers\n"
            f"    {C_DIM}Includes Race Mode, Fog of War, Hypothesis Challenge, Autopsy & Heatmaps.{C_END}"
        ),
    ),
    (
        "2",
        "treasure_solver2",
        "TSP / Treasure Hunt",
        (
            f"    {C_BIGO}Travelling Salesman Problem{C_END} on a live maze grid.\n"
            f"    Nearest Neighbour · Brute Force (Exact, N≤8) · Genetic Algorithm (GA + 2-opt)\n"
            f"    {C_DIM}Animated tour construction, crossover, mutation, and Report Card comparison.{C_END}"
        ),
    ),
    (
        "3",
        "multi_agent_solver",
        "MAPF — Multi-Agent Pathfinding",
        (
            f"    {C_BIGO}Multi-Agent Pathfinding{C_END} with conflict resolution.\n"
            f"    Independent A* (baseline) · Prioritised Planning · Conflict-Based Search (CBS)\n"
            f"    {C_DIM}Compare guarantees: no-conflict, suboptimal, vs. optimal SoC.{C_END}"
        ),
    ),
    (
        "4",
        "dynamic_solver3",
        "Pursuit-Evasion / Pac-Man",
        (
            f"    {C_BIGO}Dynamic re-planning{C_END} as a moving target evades the agent.\n"
            f"    Naive Recalculation · Dynamic Repair (D* Lite inspired) · Greedy Intercept\n"
            f"    {C_DIM}Hunter vs. prey on a live board — compare replan frequency and step counts.{C_END}"
        ),
    ),
]


# --- module loader ---

def _launch_module(module_name: str, display_title: str) -> None:
    """Load and run a module's main() function."""
    print(f"\n{C_DOT}⏳ Loading module: {C_BOLD}{display_title}{C_END}{C_DOT}…{C_END}")
    time.sleep(0.3)

    try:
        import importlib
        import sys as _sys
        # Evict any cached copy so module-level state is always fresh on relaunch
        _sys.modules.pop(module_name, None)
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        print(
            f"\n  {C_HEAD}✖  Module not found:{C_END} {C_BOLD}{module_name}.py{C_END}\n"
            f"  {C_HEAD}   Error: {exc}{C_END}\n"
            f"  {C_WALL}   Place the file in the same directory as this launcher and retry.{C_END}\n"
        )
        input(f"  👉 Press {C_PATH}ENTER{C_END} to return to the menu…")
        return

    entry = getattr(mod, "main", None)
    if not callable(entry):
        print(
            f"\n  {C_HEAD}✖  {module_name}.py has no main() function.{C_END}\n"
            f"  {C_WALL}   Add a main() entry point and try again.{C_END}\n"
        )
        input(f"  👉 Press {C_PATH}ENTER{C_END} to return to the menu…")
        return

    try:
        entry()
    except (KeyboardInterrupt, EOFError):
        print(f"\n\n  {C_DOT}↩  Returned from {display_title}.{C_END}")
        time.sleep(0.5)
    except (MemoryError, SystemExit):
        raise
    except Exception as exc:
        import traceback
        _CHILD_CRASHED.add(display_title)
        print(
            f"\n  {C_HEAD}💥  {display_title} crashed unexpectedly:{C_END}\n"
            f"  {C_HEAD}   {type(exc).__name__}: {exc}{C_END}\n"
        )
        traceback.print_exc()
        input(f"  👉 Press {C_PATH}ENTER{C_END} to return to the menu…")
    finally:
        # wipe any "Goodbye!" text left by the child before redrawing the menu
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


# --- main menu loop ---

def _master_menu() -> None:
    dispatch: dict[str, tuple[str, str]] = {
        key: (mod, title) for key, mod, title, _ in _MODULES
    }

    _splash_shown: bool = False

    while True:
        H = _term_height()
        _clear_screen()

        # If the terminal is too short to fit banner + menu together,
        # show the banner alone first as a splash screen, then switch to
        # the compact header for the rest of the session.
        if H < _FULL_DISPLAY_HEIGHT and not _splash_shown:
            top_pad = max(0, (H - _BANNER_HEIGHT) // 2)
            print("\n" * top_pad, end="")
            print(_BANNER)
            print(
                f"\n{C_GOLD}{'─' * 60}{C_END}\n"
                f"  {C_DIM}Terminal height: {H} lines  "
                f"(full layout needs {_FULL_DISPLAY_HEIGHT}){C_END}\n"
                f"{C_GOLD}{'─' * 60}{C_END}"
            )
            input(f"\n  {C_PATH}▶  Press ENTER to continue to the Encyclopedia…{C_END}  ")
            _splash_shown = True
            _clear_screen()

        if H >= _FULL_DISPLAY_HEIGHT:
            print(_BANNER)
            _splash_shown = False
        else:
            W = _term_width()
            print()
            print(_center_ansi(_COMPACT_HEADER, W))
            print()

        # menu body
        print(f"{C_GOLD}{'─' * 76}{C_END}")
        print(
            f"  {C_BOLD}{C_TITLE}SELECT A MODULE{C_END}"
            f"  {C_DIM}(each module has its own sub-menu inside){C_END}"
        )
        print(
            f"  {C_DIM}Suggested order: 1 → 2 → 3 → 4  "
            f"(Domains 3 & 4 build on A* from Domain 1){C_END}"
        )
        print(f"{C_GOLD}{'─' * 76}{C_END}")

        for key, _mod, title, desc in _MODULES:
            print(
                f"\n  {C_BOLD}{C_PATH}[{key}]{C_END}"
                f"  {C_BOLD}{title}{C_END}"
            )
            print(desc)

        print(f"\n{C_GOLD}{'─' * 76}{C_END}")
        print(
            f"  {C_BOLD}{C_HEAD}[0]{C_END}"
            f"  {C_DIM}Exit the Encyclopedia{C_END}"
        )
        print(f"{C_GOLD}{'─' * 76}{C_END}\n")

        choice = input(
            f"  {C_GOLD}▶{C_END}  Enter your choice ({C_PATH}1–4{C_END}"
            f" or {C_HEAD}0{C_END}): "
        ).strip()

        if choice == "0":
            _clear_screen()
            print(
                f"\n{C_GOLD}╔══════════════════════════════════════════════════════╗{C_END}"
                f"\n{C_GOLD}║{C_END}"
                f"  {C_BOLD}Thank you for exploring The Algorithm Encyclopedia!{C_END}"
                f"  {C_GOLD}║{C_END}"
                f"\n{C_GOLD}║{C_END}"
                f"  {C_DIM}Keep questioning. Keep visualising. Keep learning.{C_END}"
                f"   {C_GOLD}║{C_END}"
                f"\n{C_GOLD}╚══════════════════════════════════════════════════════╝{C_END}"
                f"\n"
            )
            break

        if choice in dispatch:
            module_name, display_title = dispatch[choice]
            _launch_module(module_name, display_title)
            continue

        print(f"\n  {C_HEAD}Invalid option — please enter 0–4.{C_END}")
        time.sleep(1.0)


# --- entry point ---

def main() -> None:
    try:
        _master_menu()
    except (KeyboardInterrupt, EOFError):
        print(f"\033[0m\n\n{C_DOT}Interrupted — goodbye! 🚀{C_END}\n")
    finally:
        if _CHILD_CRASHED:
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.stderr.close()
        sys.exit(0)
