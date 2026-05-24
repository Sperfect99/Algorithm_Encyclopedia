"""
_encyclopedia_launcher.py — master menu for the Algorithm Encyclopedia.

Launches the four modules on demand. Each one is imported only when selected
so startup is instant. A missing file prints a warning and falls back to the
menu rather than crashing everything.

Flags (run with --help for the full list):
  --learn          Classic Pathfinding, simplified menu
  --classic        Classic Pathfinding, full experience
  --tsp            TSP / Treasure Hunt module
  --mapf           Multi-Agent Pathfinding module
  --pursuit        Pursuit-Evasion module
  --help           Print flag descriptions and exit
"""

from __future__ import annotations

import os
import sys
import time

from ui.theme import *  # noqa: F401,F403
from ui.terminal_utils import (
    _strip_ansi, _center_ansi, _term_height, _term_width,
    clear_screen as _clear_screen,
    restore_terminal as _restore_terminal,
)

ansi_enable_windows()

# modules that crashed during this session — consulted at exit for CI exit code
_CHILD_CRASHED: set[str] = set()


# --- flag parser ---

def _parse_flags() -> dict:
    """Read sys.argv and return a dict with the session configuration.

    Unknown flags are ignored so future additions don't break older installs.
    """
    args  = sys.argv[1:]
    flags = {
        "mode":   "launcher",   # launcher | learn | classic | tsp | mapf | pursuit
    }

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--help":
            _print_help()
            sys.exit(0)
        elif arg == "--learn":
            flags["mode"] = "learn"
        elif arg == "--classic":
            flags["mode"] = "classic"
        elif arg == "--tsp":
            flags["mode"] = "tsp"
        elif arg == "--mapf":
            flags["mode"] = "mapf"
        elif arg == "--pursuit":
            flags["mode"] = "pursuit"
        i += 1

    return flags


def _print_help() -> None:
    """Print all available flags with descriptions."""
    print(f"""
{C_GOLD}Algorithm Encyclopedia — available flags{C_END}

  {C_PATH}--learn{C_END}      Opens Classic Pathfinding with a simplified menu.
               Shows algorithms 1-15 and Tutorial only.
               No Benchmark, Race Mode, Multi-run, or advanced options.
               Good first stop for anyone new to the project.

  {C_PATH}--classic{C_END}    Opens Classic Pathfinding directly with the full experience.
               Same as launching module [1] from the main menu.

  {C_PATH}--tsp{C_END}        Opens the TSP / Treasure Hunt module directly.
  {C_PATH}--mapf{C_END}       Opens the Multi-Agent Pathfinding module directly.
  {C_PATH}--pursuit{C_END}    Opens the Pursuit-Evasion module directly.

  {C_PATH}--help{C_END}       Show this message.

  {C_DIM}No flags → opens the main launcher menu (default).{C_END}

{C_DIM}Examples:
  python _encyclopedia_launcher.py
  python _encyclopedia_launcher.py --learn
  python _encyclopedia_launcher.py --classic
  python _encyclopedia_launcher.py --help{C_END}
""")
    # Pause before exit so the terminal doesn't close before the user reads it.
    # On Windows running from Explorer or cmd, the window vanishes immediately
    # after sys.exit() without this.
    try:
        input("  Press ENTER to exit…")
    except (KeyboardInterrupt, EOFError):
        pass


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

def _launch_module(module_name: str, display_title: str, **kwargs) -> None:
    """Load and run a module's main() function.

    kwargs are forwarded to main() so flags like mode='learn' reach
    the module without the launcher needing to know the details.
    """
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
        entry(**kwargs)
    except (KeyboardInterrupt, EOFError):
        _restore_terminal()
        print(f"\n\n  {C_DOT}↩  Returned from {display_title}.{C_END}")
        time.sleep(0.5)
    except (MemoryError, SystemExit):
        raise
    except Exception as exc:
        import traceback
        _restore_terminal()   # cursor and colours must be clean before printing
        _CHILD_CRASHED.add(display_title)
        print(
            f"\n  {C_HEAD}💥  {display_title} crashed unexpectedly:{C_END}\n"
            f"  {C_HEAD}   {type(exc).__name__}: {exc}{C_END}\n"
        )
        traceback.print_exc()
        input(f"  👉 Press {C_PATH}ENTER{C_END} to return to the menu…")
    finally:
        # clear any text the child left before the master menu redraws
        _restore_terminal()
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


# --- main menu loop ---

def _master_menu() -> None:
    dispatch: dict[str, tuple[str, str]] = {
        key: (mod, title) for key, mod, title, _ in _MODULES
    }

    _splash_shown: bool = False

    while True:
        W = _term_width()
        H = _term_height()

        # Soft warning — shown as a banner line in the menu rather than
        # a hard block. Lets the user still navigate and pick a module;
        # individual features block themselves if they genuinely can't fit.
        _size_warn = (
            f"  {C_BACK}⚠  Small terminal ({W}×{H}) — some features may not render correctly{C_END}"
            if W < 80 or H < 28 else ""
        )

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
        if _size_warn:
            print(_size_warn)
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
    flags = _parse_flags()
    mode  = flags["mode"]

    # Direct module shortcuts — skip the launcher menu entirely
    _DIRECT: dict[str, tuple[str, str, dict]] = {
        "learn":   ("maze_controller",    "Classic Pathfinding",          {"mode": "learn"}),
        "classic": ("maze_controller",    "Classic Pathfinding",          {}),
        "tsp":     ("treasure_solver2",   "TSP / Treasure Hunt",          {}),
        "mapf":    ("multi_agent_solver", "MAPF — Multi-Agent Pathfinding", {}),
        "pursuit": ("dynamic_solver3",    "Pursuit-Evasion",              {}),
    }

    try:
        if mode in _DIRECT:
            module_name, display_title, kwargs = _DIRECT[mode]
            _launch_module(module_name, display_title, **kwargs)
        else:
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