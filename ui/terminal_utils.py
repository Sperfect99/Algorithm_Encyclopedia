"""
ui/terminal_utils.py — terminal helpers used across all four modules.

Cursor control, screen clearing, ANSI stripping, precise sleep,
Windows timer fix, signal handling — the boring-but-necessary stuff.
"""
from __future__ import annotations

import os
import sys
import time
import unicodedata
import atexit

from ui.theme import C_HEAD, C_END

# Width of ASCII progress bars. Imported by animation.py and renderer.py
# so all bars stay the same width without manual coordination.
PROGRESS_BAR_WIDTH: int = 20



# --- WINDOWS TIMER RESOLUTION ---

def _windows_timer_init() -> None:
    """Request 1ms OS timer resolution on Windows.

    Without this, time.sleep(0.016) oscillates between 15ms and 31ms (one or
    two 64Hz timer ticks), making animations stutter. timeBeginPeriod(1) pushes
    the scheduler to 1kHz. The paired timeEndPeriod is registered in atexit so
    the system clock is restored on exit — not doing this would leave the entire
    OS at 1kHz timer resolution after the program closes.
    """
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)           # type: ignore[attr-defined]
        atexit.register(ctypes.windll.winmm.timeEndPeriod, 1)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass  # not Windows, or winmm unavailable — no-op


if sys.platform == "win32":
    _windows_timer_init()


_IS_WINDOWS: bool = sys.platform == "win32"

# Below this threshold we use the spin-lock hybrid on Windows.
# Above it, timeBeginPeriod(1) alone gives sufficient accuracy.
_SPINLOCK_THRESHOLD_S: float = 0.020  # 20ms


def precise_sleep(seconds: float) -> None:
    """High-resolution sleep suitable for 60fps animation on all platforms.

    Linux/macOS: time.sleep() already has sub-ms resolution. Called directly.

    Windows (after timeBeginPeriod(1)):
      - Delays >= 20ms: sleep directly, timer lift alone is enough.
      - Delays < 20ms: sleep for (seconds - 2ms), then spin-lock the last 2ms.
        The spin-lock burns CPU briefly but eliminates the ±1ms jitter that
        the timer lift alone can't remove. Result: ±0.05ms accuracy.
    """
    if seconds <= 0:
        return

    if not _IS_WINDOWS or seconds >= _SPINLOCK_THRESHOLD_S:
        time.sleep(seconds)
        return

    # Windows hybrid path
    deadline: float = time.perf_counter() + seconds
    coarse_s: float = seconds - 0.002
    if coarse_s > 0:
        time.sleep(coarse_s)
    while time.perf_counter() < deadline:
        pass  # spin the last ~2ms



# --- TERMINAL CLEANUP (registered with atexit) ---

def _emergency_terminal_restore() -> None:
    """Restore the terminal on exit — fires via atexit on normal exit, exceptions,
    SIGTERM, and SIGHUP. Emits: exit alt buffer + reset ANSI + show cursor."""
    try:
        import sys
        if not sys.stdout.isatty():
            return
        sys.stdout.write("\033[?1049l\033[0m\033[?25h")
        sys.stdout.flush()
    except Exception:
        pass  # stdout already closed — nothing left to do


atexit.register(_emergency_terminal_restore)


def _signal_to_systemexit(signum: int, frame: object) -> None:  # type: ignore[type-arg]
    """Convert SIGTERM/SIGHUP into SystemExit so atexit chain fires."""
    raise SystemExit(f"Terminated by signal {signum}")


if sys.platform != "win32":
    try:
        import signal as _signal
        _signal.signal(_signal.SIGTERM, _signal_to_systemexit)
        _signal.signal(_signal.SIGHUP,  _signal_to_systemexit)
    except (OSError, ValueError):
        pass  # not main thread, or signal unavailable
else:
    # signal.signal() on Windows only catches SIGINT and SIGTERM.
    # It can't intercept Ctrl+Break, window close, logoff, or shutdown.
    # SetConsoleCtrlHandler() covers all six events.
    try:
        import ctypes
        import ctypes.wintypes

        _HandlerRoutine = ctypes.WINFUNCTYPE(
            ctypes.wintypes.BOOL,
            ctypes.wintypes.DWORD,
        )

        def _win_ctrl_handler(ctrl_type: int) -> bool:
            """Convert any console control event to SystemExit so atexit runs."""
            _CTRL_NAMES = {
                0: "CTRL_C_EVENT",     1: "CTRL_BREAK_EVENT",
                2: "CTRL_CLOSE_EVENT", 5: "CTRL_LOGOFF_EVENT",
                6: "CTRL_SHUTDOWN_EVENT",
            }
            raise SystemExit(
                f"Console control event: "
                f"{_CTRL_NAMES.get(ctrl_type, f'UNKNOWN({ctrl_type})')}"
            )

        _win_ctrl_callback = _HandlerRoutine(_win_ctrl_handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(  # type: ignore[attr-defined]
            _win_ctrl_callback, ctypes.wintypes.BOOL(True)
        )
        # Keep a module-level reference — a GC'd ctypes callback causes a
        # silent segfault when Windows tries to invoke it
        _WIN_CTRL_CALLBACK = _win_ctrl_callback

    except (AttributeError, OSError):
        pass



# --- STDIN BUFFER ---

def flush_stdin() -> None:
    """Drain any keys that were buffered during animation sleeps.

    Without this, any typing during an animation gets consumed by the first
    input() call after it — skipping prompts the user never saw. Annoying
    to experience in a classroom setting.
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



# --- ALTERNATE SCREEN BUFFER ---

def enter_alt_buffer() -> None:
    """Switch to VT100 Alternate Screen Buffer on import.

    Keeps the animation out of the user's scrollback history. The atexit
    hook emits \\033[?1049l to exit the alt buffer on any termination.
    """
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?1049h")
            sys.stdout.flush()
    except (AttributeError, OSError):
        pass



# --- CURSOR VISIBILITY ---

def hide_cursor() -> None:
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25l")
            sys.stdout.flush()
    except (AttributeError, OSError):
        pass


def show_cursor() -> None:
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()
    except (AttributeError, OSError):
        pass



# --- SCREEN CLEAR ---

def clear_screen() -> None:
    """Clear the terminal screen."""
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
    except (AttributeError, OSError):
        pass



# --- ANSI STRIPPING & VISUAL WIDTH ---

def _strip_ansi(s: str) -> str:
    """Remove ANSI escape codes from a string. Single-pass, O(n), no regex.

    Handles both CSI sequences (\033[...X where X is any letter) and
    OSC sequences (\033]...\007 or \033]...\033\\). In this codebase
    only SGR codes (ending in 'm') appear in user-visible strings, but
    handling the full set prevents silent corruption if that ever changes.
    """
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == '\033' and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == '[':
                # CSI sequence — skip until we hit the final byte (any letter 0x40-0x7E)
                i += 2
                while i < len(s) and not ('A' <= s[i] <= '~'):
                    i += 1
                i += 1  # skip the final byte itself
            elif nxt == ']':
                # OSC sequence — skip until ST (\033\\) or BEL (\007)
                i += 2
                while i < len(s):
                    if s[i] == '\007':
                        i += 1
                        break
                    if s[i] == '\033' and i + 1 < len(s) and s[i + 1] == '\\':
                        i += 2
                        break
                    i += 1
            else:
                # Two-character Fe sequence (e.g. \033M = reverse index) — skip both
                i += 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def _visual_width(s: str) -> int:
    """Return the number of terminal columns occupied by string s.

    Handles wide Unicode chars (✅, 🎓, etc.) that occupy 2 columns but
    have len() == 1. Without this, ANSI-aligned column separators drift.
    Always call on the ANSI-stripped string first.
    """
    width = 0
    for ch in s:
        if unicodedata.category(ch) in ('Mn', 'Me', 'Mc'):
            continue  # zero-width combining marks
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ('W', 'F') else 1
    return width


def _center_ansi(text: str, width: int) -> str:
    """Centre text within width terminal columns, ANSI-aware.

    str.center() counts invisible escape bytes as visible characters,
    so coloured titles end up left-shifted. This measures the true
    printable width and distributes padding correctly.
    """
    vis_w   = _visual_width(_strip_ansi(text))
    padding = max(0, width - vis_w)
    left    = padding // 2
    right   = padding - left
    return " " * left + text + " " * right



# --- TERMINAL SIZE ---

def _term_height(minimum: int = 24, maximum: int = 200) -> int:
    """Current terminal height, polled live. Never cached."""
    try:
        return max(minimum, min(maximum, os.get_terminal_size().lines))
    except OSError:
        return minimum


def _term_width(minimum: int = 60, maximum: int = 120) -> int:
    """Current terminal width, polled live. Never cached.

    Call this at the top of each menu loop iteration, not once and stored.
    That's the correct fix for stale dimension issues when the user resizes.
    """
    try:
        return max(minimum, min(maximum, os.get_terminal_size().columns))
    except OSError:
        return minimum


def _check_terminal_size(
    maze_rows: int,
    maze_cols: int,
    col_pad:   int = 0,
    row_pad:   int = 5,
) -> None:
    """Warn (and optionally abort) if the terminal is too small for the maze."""
    try:
        term = os.get_terminal_size()
    except OSError:
        return

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


# Enter the Alternate Screen Buffer immediately on import so clear_screen()
# never touches the user's primary scrollback buffer
enter_alt_buffer()
