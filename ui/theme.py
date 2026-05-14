"""
ui/theme.py — all ANSI colour constants live here and nowhere else.

If you're adding a new colour, add it here. Algorithm files should never
contain raw escape codes — that way changing the colour scheme is a one-file job.
"""
from __future__ import annotations

import os
import sys


def ansi_enable_windows() -> None:
    """Sort out Windows terminal weirdness so the app doesn't look broken.

    Three separate things to fix on Windows:
      1. ANSI colours: os.system("") flips on ENABLE_VIRTUAL_TERMINAL_PROCESSING.
      2. QuickEdit Mode: if the user accidentally clicks the terminal window it
         freezes the whole animation. We disable that via kernel32. A bit low-level
         but it's the only reliable way.
      3. UTF-8: cmd.exe defaults to cp1252 which crashes on any emoji or box-drawing
         char. We force UTF-8 with replacement fallback so it degrades gracefully.
    """
    if sys.platform == "win32":
        rc = os.system("")  # triggers ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if rc != 0:
            # VT100 activation failed — kill all ANSI so we don't print garbage
            global _ANSI
            _ANSI = False

        # Disable QuickEdit Mode — clicking the terminal window suspends the
        # process mid-animation otherwise. Annoying to discover the hard way.
        try:
            import ctypes
            import ctypes.wintypes
            kernel32 = ctypes.windll.kernel32
            STD_INPUT_HANDLE      = ctypes.wintypes.DWORD(-10)
            ENABLE_QUICK_EDIT     = 0x0040
            ENABLE_EXTENDED_FLAGS = 0x0080
            handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
            mode   = ctypes.wintypes.DWORD(0)
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                new_mode = (mode.value & ~ENABLE_QUICK_EDIT) | ENABLE_EXTENDED_FLAGS
                kernel32.SetConsoleMode(handle, ctypes.wintypes.DWORD(new_mode))
        except Exception:
            pass  # not Windows, or stdin is redirected — safe to ignore

    # Force UTF-8 on ALL platforms (not just Windows).
    # Linux with a C locale will also crash on box-drawing chars without this.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # piped/redirected stream — nothing we can do


def _ansi_supported() -> bool:
    """Return True if it's actually worth emitting escape codes."""
    if os.environ.get("NO_COLOR") is not None:
        return False  # respect the NO_COLOR standard
    if not sys.stdout.isatty():
        return False  # piped to a file or CI — no point colouring it
    if sys.platform == "win32":
        try:
            if os.system("") != 0:
                return False
        except Exception:
            return False
    return True


# All C_* constants are always defined — callers never need to guard against
# missing names. On non-TTY environments they're just empty strings.
_ANSI = _ansi_supported()

# ── Reset ─────────────────────────────────────────────────────────────────────
C_END   = "\033[0m" if _ANSI else ""

# ── Phase 1: classic pathfinding colours ──────────────────────────────────────
# C_WALL uses paired FG+BG (both index 240) so the █ block looks solid on
# dark themes like Dracula/Nord where pure-FG would blend into the background.
C_WALL  = "\033[38;5;240;48;5;240m" if _ANSI else ""
C_DOT   = "\033[38;5;244m" if _ANSI else ""   # mid grey   — explored cells
C_BACK  = "\033[38;5;209m" if _ANSI else ""   # salmon     — fog banner / warnings
C_HEAD  = "\033[38;5;214m" if _ANSI else ""   # gold       — frontier marker '@'
C_PATH  = "\033[38;5;82m"  if _ANSI else ""   # bright green — solution path
C_START = "\033[38;5;226m" if _ANSI else ""   # yellow     — S and E terminals
C_MUD   = "\033[38;5;130m" if _ANSI else ""   # brown      — mud terrain '~'
# Same paired FG+BG trick for fog cells (near-black bg hides unvisited cells)
C_FOG   = "\033[38;5;238;48;5;238m" if _ANSI else ""
C_DUEL2 = "\033[38;5;39m"  if _ANSI else ""   # sky-blue   — Challenger 2
C_HYP   = "\033[38;5;207m" if _ANSI else ""   # pink       — Hypothesis mode
C_RACE  = "\033[38;5;196m" if _ANSI else ""   # bright red — Race Mode heading
C_BIGO  = "\033[38;5;159m" if _ANSI else ""   # ice-blue   — Big-O HUD text
C_PQ    = "\033[38;5;220m" if _ANSI else ""   # amber      — PQ Inspector text

# ── Phase 3: multi-agent colours ──────────────────────────────────────────────
# Picked to be distinguishable from each other AND from Phase-1 colours.
# TODO: if someone adds a 4th agent these run out — extend the AGENT_COLORS
#       tuple and add C_AGENT3/C_GOAL3 here.
C_AGENT0 = "\033[38;5;46m"  if _ANSI else ""  # vivid green  — Agent 0
C_AGENT1 = "\033[38;5;33m"  if _ANSI else ""  # azure blue   — Agent 1
C_AGENT2 = "\033[38;5;208m" if _ANSI else ""  # vivid orange — Agent 2

# Goal markers are intentionally dimmer than agent markers for visual hierarchy
C_GOAL0 = "\033[38;5;28m"  if _ANSI else ""   # dark green  — Agent 0 goal
C_GOAL1 = "\033[38;5;25m"  if _ANSI else ""   # dark blue   — Agent 1 goal
C_GOAL2 = "\033[38;5;94m"  if _ANSI else ""   # dark orange — Agent 2 goal

C_CONFLICT  = "\033[38;5;196m" if _ANSI else ""  # bright red — vertex collision
C_TARGET    = "\033[38;5;201m" if _ANSI else ""  # magenta    — pursuit target
C_INTERCEPT = "\033[38;5;51m"  if _ANSI else ""  # cyan       — predicted intercept

C_PLAN_OK   = "\033[38;5;82m"  if _ANSI else ""  # green — CBS node is conflict-free
C_PLAN_FAIL = "\033[38;5;196m" if _ANSI else ""  # red   — CBS node still has conflicts

# ── Phase 4: TSP / Treasure Hunt colours ──────────────────────────────────────
C_TREASURE  = "\033[38;5;220m" if _ANSI else ""  # amber-gold   — uncollected treasure
C_COLLECTED = "\033[38;5;28m"  if _ANSI else ""  # forest green — collected treasure
C_GA_LIVE   = "\033[38;5;44m"  if _ANSI else ""  # teal         — GA ghost-path overlay
C_STAT      = "\033[38;5;117m" if _ANSI else ""  # sky blue     — stats / key metrics

# Convenience tuples — MAPF controllers index by agent id
AGENT_COLORS: tuple[str, ...] = (C_AGENT0, C_AGENT1, C_AGENT2)
GOAL_COLORS:  tuple[str, ...] = (C_GOAL0,  C_GOAL1,  C_GOAL2)

# ── Launcher / banner colours ──────────────────────────────────────────────────
C_TITLE = "\033[38;5;226m" if _ANSI else ""  # yellow  — big ASCII art title
C_GOLD  = "\033[38;5;214m" if _ANSI else ""  # gold    — banner border
C_DIM   = "\033[38;5;244m" if _ANSI else ""  # dim     — secondary/hint text
C_BOLD  = "\033[1m"        if _ANSI else ""  # bold    — emphasis
C_EMBER = "\033[38;5;202m" if _ANSI else ""  # orange  — "BETA" style accents
C_BRIGHT_GREEN = "\033[38;5;46m" if _ANSI else ""
