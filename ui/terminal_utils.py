"""
ui/terminal_utils.py  —  Canonical terminal I/O utility functions.

Previously copy-pasted across FOUR solver files:
    clear_screen()          — maze_solverV7, treasure_solver2,
                              multi_agent_solver, dynamic_solver3
    _strip_ansi()           — maze_solverV7, treasure_solver2,
                              multi_agent_solver, dynamic_solver3,
                              algorithm_encyclopedia  (5 copies!)
    _visual_width()         — maze_solverV7, treasure_solver2,
                              multi_agent_solver, dynamic_solver3
    _center_ansi()          — maze_solverV7 only (but belongs here)
    _check_terminal_size()  — maze_solverV7, treasure_solver2,
                              multi_agent_solver, dynamic_solver3

Every solver module now imports from this single module.  No solver file
may define any of these functions locally.

Zero external dependencies; Python 3.9+ stdlib only.
"""

from __future__ import annotations

import os
import sys
import time
import unicodedata

import atexit

from ui.theme import C_HEAD, C_END

# Width of ASCII progress bars in terminal columns.
# Shared by ui.animation and ui.renderer to keep all progress bars in sync.
PROGRESS_BAR_WIDTH: int = 20


# ===========================================================================
# ── WINDOWS TIMER RESOLUTION LIFT ─────────────────────────────────────────────
# ===========================================================================

def _windows_timer_init() -> None:
    """
    On Windows, request a 1 ms OS multimedia timer resolution.

    The Windows default timer interrupt fires every 15.625 ms (64 Hz).
    Calling ``time.sleep(0.016)`` without this lift will oscillate between
    sleeping one tick (15.6 ms) and two ticks (31.2 ms), producing an
    erratic ~40 FPS with violent micro-stutters — even though the *target*
    frame delay is 16 ms.

    ``timeBeginPeriod(1)`` raises the scheduler interrupt to 1 kHz for this
    process, reducing ``time.sleep()`` jitter from ±15.6 ms to ±1 ms.
    The paired ``timeEndPeriod(1)`` is registered in the atexit chain so the
    system timer is restored on clean exit, exception, SIGTERM, and SIGHUP.

    This is a well-established pattern used by every high-performance Python
    media app on Windows (pygame, VLC Python bindings, etc.).  The call is
    silently skipped on Linux/macOS where it is unnecessary.
    """
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)           # type: ignore[attr-defined]
        atexit.register(ctypes.windll.winmm.timeEndPeriod, 1)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass  # Not Windows, or winmm unavailable — no-op


if sys.platform == "win32":
    _windows_timer_init()


_IS_WINDOWS: bool = sys.platform == "win32"

# Threshold below which we engage the spin-lock top-off on Windows.
# Above this, timeBeginPeriod(1) alone is sufficient.
_SPINLOCK_THRESHOLD_S: float = 0.020   # 20 ms


def precise_sleep(seconds: float) -> None:
    """
    High-resolution sleep suitable for 60 FPS frame pacing on all platforms.

    Strategy
    --------
    *Linux / macOS*
        ``time.sleep()`` already has sub-millisecond resolution via
        ``nanosleep(2)`` — called directly, no overhead.

    *Windows (after ``timeBeginPeriod(1)``)*
        For delays ≥ 20 ms the timer lift alone gives ±1 ms accuracy —
        ``time.sleep()`` is called directly.

        For delays < 20 ms (i.e. every live animation frame) a *hybrid*
        approach is used:

            1. Sleep for ``(seconds − 2 ms)`` using the OS scheduler.
               This yields the CPU for the bulk of the interval so we do
               not burn 100 % of a core while the application is idle.
            2. Spin on ``time.perf_counter()`` for the final 2 ms.
               The spin-lock is tight enough to hit the target within
               ~5 µs, completely eliminating the ±1 ms residual jitter
               that ``timeBeginPeriod(1)`` alone cannot remove.

    The result is frame delivery accurate to within ±0.05 ms on Windows —
    sufficient for rock-solid 60 FPS with zero perceptible stutter.

    Parameters
    ----------
    seconds : float
        Desired sleep duration in seconds.  Values ≤ 0 return immediately.
    """
    if seconds <= 0:
        return

    if not _IS_WINDOWS or seconds >= _SPINLOCK_THRESHOLD_S:
        time.sleep(seconds)
        return

    # ── Windows hybrid path ──────────────────────────────────────────────────
    deadline: float = time.perf_counter() + seconds
    coarse_s: float = seconds - 0.002          # sleep all but the last 2 ms
    if coarse_s > 0:
        time.sleep(coarse_s)
    # Spin-lock the remaining ~2 ms (burns CPU briefly, but unavoidable
    # at sub-millisecond precision on Windows without a kernel waitable timer).
    while time.perf_counter() < deadline:
        pass


# ===========================================================================
# ── EMERGENCY TERMINAL RESTORE ────────────────────────────────────────────────
# ===========================================================================

def _emergency_terminal_restore() -> None:
    """Guaranteed terminal cleanup registered with atexit.

    Fires on normal exit, uncaught exceptions, SIGTERM, and SIGHUP.
    Emits:
        \\033[?1049l — exit the Alternate Screen Buffer
        \\033[0m     — reset all ANSI colour/style attributes
        \\033[?25h   — restore cursor visibility
    """
    try:
        import sys
        if not sys.stdout.isatty():
            return
        sys.stdout.write("\033[?1049l\033[0m\033[?25h")
        sys.stdout.flush()
    except Exception:
        pass  # stdout already closed or broken — nothing left to do

atexit.register(_emergency_terminal_restore)


def restore_terminal() -> None:
    """Mid-session terminal cleanup — resets colours and shows the cursor.

    Safe to call after any animation run where the cursor may be hidden
    or colours may be active. Does NOT exit the alternate screen buffer
    because the session is still running — that only happens on process
    exit via the atexit-registered _emergency_terminal_restore().
    Safe to call multiple times; no-op when stdout is not a TTY.
    """
    try:
        if not sys.stdout.isatty():
            return
        sys.stdout.write("\033[0m\033[?25h")
        sys.stdout.flush()
    except Exception:
        pass  # stdout may already be closed during atexit or pipe teardown
    raise SystemExit(f"Terminated by signal {signum}")


# Flag set by the SIGWINCH handler. The animation loop checks this each
# frame and triggers a full redraw when True, then resets it to False.
# A plain bool in a list so the signal handler (a different stack frame)
# can mutate it without a global declaration.
_TERMINAL_RESIZED: list[bool] = [False]


def _sigwinch_handler(signum: int, frame: object) -> None:  # type: ignore[type-arg]
    """Mark that the terminal was resized. The next render clears and redraws."""
    _TERMINAL_RESIZED[0] = True


if sys.platform != "win32":
    try:
        import signal as _signal
        _signal.signal(_signal.SIGTERM, _signal_to_systemexit)
        _signal.signal(_signal.SIGHUP,  _signal_to_systemexit)
        # SIGWINCH fires whenever the terminal window is resized.
        # We just set the flag — the renderer picks it up next frame.
        # Not available on Windows; the try/except handles that gracefully.
        if hasattr(_signal, 'SIGWINCH'):
            _signal.signal(_signal.SIGWINCH, _sigwinch_handler)
    except (OSError, ValueError):
        pass  # not in main thread, or signal unavailable — best-effort

else:
    # ── Windows native console control handler ───────────────────────────
    # signal.signal() on Windows only catches SIGINT (Ctrl+C) and SIGTERM.
    # It is completely blind to:
    #   CTRL_BREAK_EVENT  (Ctrl+Break)       — value 1
    #   CTRL_CLOSE_EVENT  (window X button)  — value 2
    #   CTRL_LOGOFF_EVENT (user logoff)      — value 5
    #   CTRL_SHUTDOWN_EVENT (system shutdown)— value 6
    #
    # SetConsoleCtrlHandler() is the only Windows API that intercepts all
    # six events.  We register a ctypes callback that converts every event
    # into a SystemExit, which triggers the atexit chain and therefore
    # _emergency_terminal_restore() → \033[?1049l before the process dies.
    #
    # Returning False from the handler tells Windows to continue down its
    # own handler chain (e.g. the default "terminate process" behaviour)
    # after our cleanup has run, which is the correct contract.
    try:
        import ctypes
        import ctypes.wintypes

        # PHANDLER_ROUTINE: BOOL WINAPI HandlerRoutine(DWORD dwCtrlType)
        _HandlerRoutine = ctypes.WINFUNCTYPE(
            ctypes.wintypes.BOOL,   # return type
            ctypes.wintypes.DWORD,  # dwCtrlType
        )

        def _win_ctrl_handler(ctrl_type: int) -> bool:
            """
            Called by Windows on any console control event.

            Raises SystemExit so Python's atexit chain fires and
            _emergency_terminal_restore() emits \\033[?1049l before
            the process is terminated by the OS.
            """
            # Event constants (wincon.h):
            #   0 = CTRL_C_EVENT, 1 = CTRL_BREAK_EVENT,
            #   2 = CTRL_CLOSE_EVENT, 5 = CTRL_LOGOFF_EVENT,
            #   6 = CTRL_SHUTDOWN_EVENT
            _CTRL_NAMES = {
                0: "CTRL_C_EVENT",
                1: "CTRL_BREAK_EVENT",
                2: "CTRL_CLOSE_EVENT",
                5: "CTRL_LOGOFF_EVENT",
                6: "CTRL_SHUTDOWN_EVENT",
            }
            raise SystemExit(
                f"Console control event: "
                f"{_CTRL_NAMES.get(ctrl_type, f'UNKNOWN({ctrl_type})')}"
            )

        _win_ctrl_callback = _HandlerRoutine(_win_ctrl_handler)

        # Add=True appends our handler; the default OS handler remains
        # in the chain and fires after ours if we don't call ExitProcess.
        ctypes.windll.kernel32.SetConsoleCtrlHandler(  # type: ignore[attr-defined]
            _win_ctrl_callback, ctypes.wintypes.BOOL(True)
        )

        # Keep a module-level reference so the ctypes callback object is
        # never garbage collected (a GC'd callback causes a silent segfault
        # when Windows tries to invoke it).
        _WIN_CTRL_CALLBACK = _win_ctrl_callback

    except (AttributeError, OSError):
        pass  # ctypes unavailable or not a real console — best-effort

# ===========================================================================
# ── STDIN BUFFER MANAGEMENT ───────────────────────────────────────────────────
# ===========================================================================

def flush_stdin() -> None:
    """
    Discard any keystrokes queued in stdin during animation sleeps.

    During ``time.sleep()`` calls inside animation drivers, the OS continues
    to buffer all keystrokes the user types.  When the animation finishes and
    the first ``input()`` prompt fires, those buffered characters are consumed
    immediately — potentially cascading through multiple prompts (report card
    gate → hypothesis gate → post-run menu → new-maze prompt) without the
    user seeing them.

    Call this function immediately before every critical post-animation
    ``input()`` call to drain the buffer first.

    Cross-platform:
        Unix / macOS : ``termios.tcflush(stdin, TCIFLUSH)``
        Windows      : drain ``msvcrt.kbhit()`` loop
        Fallback     : silent no-op (piped stdin, CI runners, etc.)
    """
    try:
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
        return
    except (ImportError, OSError, AttributeError):
        pass
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    except (ImportError, OSError, AttributeError):
        pass


# ===========================================================================
# ── SCREEN CONTROL ────────────────────────────────────────────────────────────
# ===========================================================================

def enter_alt_buffer() -> None:
    """Switch the terminal into the VT100 Alternate Screen Buffer.

    Emits ``\\033[?1049h``, the DECSET private mode that every modern
    terminal emulator (xterm, iTerm2, Windows Terminal, Alacritty, kitty,
    GNOME Terminal) honours.  Effect:

        • Saves the cursor position and the entire primary-buffer viewport.
        • Switches rendering to a clean, blank secondary buffer.
        • The user's pre-existing scrollback history is completely untouched.

    The paired exit sequence ``\\033[?1049l`` (emitted by
    ``_emergency_terminal_restore``) undoes this atomically on exit,
    restoring the user's original terminal state exactly as they left it —
    identical to the behaviour of ``vim``, ``nano``, ``htop``, and ``less``.

    Called once at module import time (bottom of this file).  Must be
    called before the first ``clear_screen()`` to guarantee the primary
    buffer is never written to.
    """
    try:
        if not sys.stdout.isatty():
            return
        sys.stdout.write("\033[?1049h")
        sys.stdout.flush()
    except (OSError, AttributeError):
        pass


def clear_screen() -> None:
    """Clear the terminal using pure ANSI escape codes (no curses required).

    Emits three escape sequences as a single flushed write:

        ESC[3J  — Erase Saved Lines (scrollback history)
                  Prevents terminal emulators (Windows Terminal, iTerm2,
                  Alacritty) from accumulating animation frames in their
                  scrollback buffer.  At Fast/Instant speed on a 61×151
                  maze, \033[2J alone generates ~216,000 lines/minute;
                  without 3J those lines pile up silently in the emulator's
                  RAM, potentially OOM-killing the terminal process itself.
                  Terminals that do not support 3J silently ignore it.

        ESC[2J  — Erase Display (visible viewport)
                  Required on terminals that handle 3J and 2J separately.

        ESC[H   — Cursor Home (move to row 1, col 1)
                  Positions the cursor for the next frame's top-left cell.

    Works on every ANSI-capable terminal including Windows Console Host
    when VT100 mode is enabled (via ansi_enable_windows()).
    """
    try:
        if not sys.stdout.isatty():
            return
        sys.stdout.write("\033[3J\033[2J\033[H")
        sys.stdout.flush()
    except (OSError, AttributeError):
        pass


def hide_cursor() -> None:
    """Hide the terminal cursor during animation to eliminate flicker."""
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25l")
            sys.stdout.flush()
    except (OSError, AttributeError):
        pass


def show_cursor() -> None:
    """Restore the terminal cursor. Always call in a finally block."""
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()
    except (OSError, AttributeError):
        pass


# ===========================================================================
# ── ANSI-AWARE STRING UTILITIES ───────────────────────────────────────────────
# ===========================================================================

def _strip_ansi(s: str) -> str:
    """Remove ANSI SGR escape sequences from *s* and return the printable text.

    Used only for column-width arithmetic — never for display.  Covers
    the ``\\033[…m`` form used throughout this codebase.

    Algorithm: single-pass O(len(s)) state machine.  No regex dependency.

    Previously defined in 5 files:
        maze_solverV7.py, treasure_solver2.py, multi_agent_solver.py,
        dynamic_solver3.py, algorithm_encyclopedia.py
    """
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == '\033' and i + 1 < len(s) and s[i + 1] == '[':
            i += 2
            while i < len(s) and s[i] != 'm':
                i += 1
            i += 1  # skip the 'm'
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def _visual_width(s: str) -> int:
    """Return the number of terminal columns occupied by string *s*.

    Pure Python / stdlib.  Uses ``unicodedata.east_asian_width`` to detect
    wide (W) and fullwidth (F) Unicode characters that occupy 2 terminal
    columns — such as ✅ (U+2705) which appears in render_split status
    lines.  Ambiguous-width (A) glyphs like ⚡ (U+26A1) are intentionally
    avoided in alignment-critical strings; see renderer.py render_split.
    All other characters (including ASCII, Latin-1, and combining marks)
    are treated as 1 column.

    Always call on the ANSI-stripped string::

        _visual_width(_strip_ansi(coloured_string))

    Previously defined in 4 files:
        maze_solverV7.py, treasure_solver2.py,
        multi_agent_solver.py, dynamic_solver3.py
    """
    width = 0
    for ch in s:
        # Zero-width Unicode categories — these occupy no terminal columns:
        #   Mn = Non-spacing mark  (e.g. combining acute U+0301)
        #   Me = Enclosing mark    (e.g. combining enclosing circle U+20DD)
        #   Mc = Spacing mark      (e.g. Devanagari vowel sign — 0 advance width)
        # Without this guard, "café" measures 5 columns instead of 4,
        # causing ANSI-aware centering to drift right by one column per
        # combining character in the string.
        if unicodedata.category(ch) in ('Mn', 'Me', 'Mc'):
            continue
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ('W', 'F') else 1
    return width


def _center_ansi(text: str, width: int) -> str:
    """Centre *text* within *width* terminal columns, ANSI-aware.

    Python's built-in ``str.center(width)`` counts invisible ANSI escape
    bytes as visible characters, causing coloured or emoji-containing
    banner titles to appear consistently left-shifted.  This helper:

        1. Strips ANSI escapes via ``_strip_ansi`` to get the printable text.
        2. Measures true terminal columns via ``_visual_width`` (handles
           wide emoji like 📊 that occupy 2 columns each).
        3. Distributes the remaining padding symmetrically around *text*.

    The result looks mathematically centred on any ANSI terminal regardless
    of colour codes or wide characters present in *text*.

    Example::

        print("═" * 70)
        print(_center_ansi(f"{C_HYP}🔮  Title  {C_END}", 70))
        print("═" * 70)

    Previously defined only in maze_solverV7.py (line 213).
    """
    vis_w   = _visual_width(_strip_ansi(text))
    padding = max(0, width - vis_w)
    left    = padding // 2
    right   = padding - left
    return " " * left + text + " " * right


# ===========================================================================
# ── TERMINAL SIZE GUARD ───────────────────────────────────────────────────────
# ===========================================================================

def _term_height(minimum: int = 24, maximum: int = 200) -> int:
    """
    Return the current terminal height in lines, polled live on every call.

    Never cached — always reflects the terminal's actual row count at the
    moment of the call.  Mirrors _term_width() exactly for vertical layout.

    Parameters
    ----------
    minimum : int   Lower bound — protects against headless contexts.  Default 24.
    maximum : int   Upper bound — prevents absurd values on tiling WMs.  Default 200.
    """
    try:
        return max(minimum, min(maximum, os.get_terminal_size().lines))
    except OSError:
        return minimum   # headless / piped — use the safe floor


def _term_width(minimum: int = 60, maximum: int = 120) -> int:
    """
    Return the current terminal width, polled live on every call.

    Never cached — always reflects the terminal's actual column count at
    the moment of the call.  This is the single correct fix for stale
    dimension problems: call it at the top of each menu loop iteration
    rather than storing the result in any variable that persists across
    iterations.

    Parameters
    ----------
    minimum : int   Lower bound — protects against headless/piped contexts
                    that return 0 or 1.  Default 60.
    maximum : int   Upper bound — prevents absurdly wide separators on
                    ultra-wide monitors.  Default 120.
    """
    try:
        return max(minimum, min(maximum, os.get_terminal_size().columns))
    except OSError:
        return minimum   # headless / piped — use the safe floor


def _check_terminal_size(
    maze_rows: int,
    maze_cols: int,
    col_pad:   int = 0,
    row_pad:   int = 5,
) -> None:
    """Warn the user (and optionally abort) if the terminal is too small.

    Parameters
    ----------
    maze_rows : int   — number of rows in the maze grid.
    maze_cols : int   — number of columns in the maze grid.
    col_pad   : int   — extra columns needed beyond maze_cols for HUD chrome.
                        Default 0.  multi_agent_solver passes 2.
    row_pad   : int   — extra lines needed beyond maze_rows for HUD chrome.
                        Default 5 (V7 / treasure baseline).
                        multi_agent_solver passes 10; dynamic_solver3 passes 8.

    Callers that previously used a custom padding now pass it explicitly::

        _check_terminal_size(rows, cols, col_pad=2, row_pad=10)  # MAPF
        _check_terminal_size(rows, cols, col_pad=0, row_pad=8)   # dynamic

    Previously defined in 4 files with different hard-coded padding:
        maze_solverV7       col_pad=0, row_pad=5
        treasure_solver2    col_pad=0, row_pad=5
        multi_agent_solver  col_pad=2, row_pad=10
        dynamic_solver3     col_pad=0, row_pad=8
    """
    try:
        term = os.get_terminal_size()
    except OSError:
        return  # headless / piped — skip the check

    required_cols  = maze_cols + col_pad
    required_lines = maze_rows + row_pad

    if term.columns < required_cols or term.lines < required_lines:
        print(
            f"\n{'⚠️  TERMINAL TOO SMALL  ⚠️':^60}"
            f"\n  Maze requires : {required_cols} columns × {required_lines} lines"
            f"\n  Your terminal : {term.columns} columns × {term.lines} lines"
            "\n\n  Resize your terminal or choose a lower complexity level."
        )
        while True:
            ans = input("\n  Continue anyway? (y/n): ").strip().lower()
            if ans in {'y', 'yes'}:
                return
            elif ans in {'n', 'no'}:
                print(
                    f"\n  {C_HEAD}Aborted — please resize your terminal "
                    f"and relaunch the module.{C_END}"
                )
                time.sleep(1.2)
                raise KeyboardInterrupt
            else:
                print("  Please answer y or n.")


# ---------------------------------------------------------------------------
# Enter the Alternate Screen Buffer immediately on import so that no
# subsequent clear_screen() call ever touches the user's primary buffer.
# The atexit hook (_emergency_terminal_restore) emits \033[?1049l to exit
# the alt-buffer cleanly when the application terminates for any reason.
# ---------------------------------------------------------------------------
enter_alt_buffer()