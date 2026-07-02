"""
PANDA Vision — Layer 1: Windows UI Automation Engine
======================================================
Uses the `uiautomation` library (a Python wrapper around the native
Windows IUIAutomation COM API) to query the live accessibility tree.

No screenshots, no templates, no hardcoding.
Elements are discovered dynamically at runtime.

Why this is better than template matching:
  - Works on ANY app without pre-captured screenshots
  - Not affected by resolution, DPI, or theme changes
  - Returns semantic metadata: element name, type, state, PID
  - Same API screen readers (NVDA, JAWS) use — very reliable on Win32/UWP

Built by Aryan — PANDA Vision Sprint 7+
"""

import threading
import time

# win32gui lets us enumerate windows in Z-order (topmost = most recently active).
# This is the fix for "PANDA sees the terminal instead of my other window":
# GetFocusedControl() always returns the terminal when the user types,
# but Z-order gives us the window the user was JUST looking at.
try:
    import win32gui   # pyrefly: ignore [missing-import]
    import win32con   # pyrefly: ignore [missing-import]
    _WIN32_AVAILABLE = True
except Exception:
    win32gui = None
    win32con = None
    _WIN32_AVAILABLE = False

_ua_lock = threading.Lock()
_ua = None          # lazy-loaded uiautomation module
_UA_AVAILABLE = False


def _get_ua():
    """Lazy-load uiautomation so the import doesn't block startup."""
    global _ua, _UA_AVAILABLE
    if _ua is not None:
        return _ua
    with _ua_lock:
        if _ua is None:
            try:
                import uiautomation as ua  # pyrefly: ignore [missing-import]
                # Suppress uiautomation's verbose debug output
                ua.SetGlobalSearchTimeout(3.0)
                _ua = ua
                _UA_AVAILABLE = True
                print("  \033[36m[UIAuto] Windows UI Automation ready.\033[0m", flush=True)
            except Exception as e:
                # Catches: ImportError (not installed), OSError/RuntimeError
                # (COM init failure), or any other startup error.
                if isinstance(e, ImportError):
                    msg = "uiautomation not installed. Run: pip install uiautomation"
                else:
                    msg = f"UI Automation init failed: {e}"
                print(
                    f"  \033[33m[UIAuto] {msg} — Layer 1 disabled.\033[0m",
                    flush=True
                )
    return _ua


def is_available() -> bool:
    """Returns True if uiautomation is installed and usable."""
    return _get_ua() is not None


# ─── Window Discovery ─────────────────────────────────────────────────────────

def list_windows() -> list[dict]:
    """
    Returns a list of all currently visible top-level windows.
    Each entry: {"title": str, "class_name": str, "pid": int}
    """
    ua = _get_ua()
    if ua is None:
        return []

    results = []
    try:
        desktop = ua.GetRootControl()
        for win in desktop.GetChildren():
            title = win.Name.strip()
            if title:
                results.append({
                    "title":      title,
                    "class_name": win.ClassName,
                    "pid":        win.ProcessId,
                })
    except Exception as e:
        print(f"  [UIAuto] Error listing windows: {e}")
    return results


# Class names of windows we should SKIP when looking for "what the user was
# viewing" — these are PANDA's own terminal / the IDE running it.
_TERMINAL_CLASS_NAMES = {
    "ConsoleWindowClass",      # cmd.exe / python.exe terminal
    "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal (wt.exe)
    "PseudoConsoleWindow",     # VS Code integrated terminal
    "VirtualConsoleClass",
}


def get_focused_window() -> dict | None:
    """
    Returns the window the user is most actively working in.

    Strategy:
      1. Use win32gui to get the active foreground window. If it's a desktop window,
         report it. If it's not a terminal window, report it directly.
      2. If it is PANDA's own terminal window, enumerate visible windows in Z-order
         and find the first non-terminal window.
      3. Fall back to uiautomation GetFocusedControl() if win32gui fails.
    """
    # ── Strategy 1: Z-order via win32gui (preferred) ──────────────────────
    if _WIN32_AVAILABLE:
        try:
            # Check immediate foreground window
            fore_hwnd = win32gui.GetForegroundWindow()
            if fore_hwnd:
                title = win32gui.GetWindowText(fore_hwnd).strip()
                cls = win32gui.GetClassName(fore_hwnd)
                
                # If foreground is desktop
                if cls in ("Progman", "WorkerW") or title.lower() in ("program manager", "desktop"):
                    return {
                        "title": "Desktop",
                        "class_name": cls,
                        "pid": None,
                        "control_type": "PaneControl"
                    }
                
                # If foreground is a user app (not a terminal running PANDA)
                if cls not in _TERMINAL_CLASS_NAMES and title:
                    return {
                        "title": title,
                        "class_name": cls,
                        "pid": None,
                        "control_type": "WindowControl"
                    }

            # If foreground was terminal, find the previous active window in Z-order
            candidates = []

            def _enum_cb(hwnd, _):
                if not win32gui.IsWindowVisible(hwnd):
                    return
                t = win32gui.GetWindowText(hwnd).strip()
                c = win32gui.GetClassName(hwnd)
                
                # Skip terminal classes
                if c in _TERMINAL_CLASS_NAMES:
                    return
                # Map desktop classes to Desktop
                if c in ("Progman", "WorkerW") or t.lower() in ("program manager", "desktop"):
                    candidates.append({"hwnd": hwnd, "title": "Desktop", "class_name": c})
                    return
                if t.lower() in ("taskbar", ""):
                    return
                candidates.append({"hwnd": hwnd, "title": t, "class_name": c})

            win32gui.EnumWindows(_enum_cb, None)

            if candidates:
                return {
                    "title":        candidates[0]["title"],
                    "class_name":   candidates[0]["class_name"],
                    "pid":          None,
                    "control_type": "WindowControl",
                }
        except Exception as e:
            print(f"  [UIAuto] win32gui Z-order failed: {e}, falling back.")

    # ── Strategy 2: uiautomation GetFocusedControl() (fallback) ───────────
    ua = _get_ua()
    if ua is None:
        return None

    try:
        focused = ua.GetFocusedControl()
        if focused is None:
            return None

        # Walk up to the top-level window
        ctrl = focused
        while ctrl.ControlType != ua.ControlType.WindowControl:
            parent = ctrl.GetParentControl()
            if parent is None or parent.ControlType == ua.ControlType.PaneControl:
                break
            ctrl = parent

        return {
            "title":        ctrl.Name.strip(),
            "class_name":   ctrl.ClassName,
            "pid":          ctrl.ProcessId,
            "control_type": ctrl.ControlTypeName,
        }
    except Exception as e:
        print(f"  [UIAuto] Error getting focused window: {e}")
        return None

# ─── Element Search ───────────────────────────────────────────────────────────

# Control types we consider "interactive" and return in search results
_INTERACTIVE_TYPES = {
    "ButtonControl", "CheckBoxControl", "ComboBoxControl",
    "EditControl", "HyperlinkControl", "ListItemControl",
    "MenuItemControl", "RadioButtonControl", "TabItemControl",
    "TextControl", "ToolBarControl", "TreeItemControl",
}

_STRUCTURAL_TYPES = {
    "PaneControl", "DocumentControl", "GroupControl", "ImageControl",
}

_SEARCH_TIMEOUT = 3.0   # seconds to wait for UI Automation search


def find_element(query: str) -> dict | None:
    """
    Layer 1 — Searches the entire accessibility tree for a UI element
    whose name contains `query` (case-insensitive).

    Search order (fastest → broadest):
      1. Focused window's children first (most likely location)
      2. All top-level windows
      3. Desktop-wide deep search (slow, last resort)

    Returns a dict on success:
      {
        "name":         str,   # element's accessible name
        "control_type": str,   # e.g. "ButtonControl", "EditControl"
        "bbox":         [x1, y1, x2, y2],  # screen coordinates
        "pid":          int,
        "source":       "ui_automation"
      }
    Returns None if not found.
    """
    ua = _get_ua()
    if ua is None:
        return None

    query_lower = query.lower().strip()
    if not query_lower:
        return None

    try:
        desktop = ua.GetRootControl()

        # ── Pass 1: search inside focused (active) window ──────────────────
        result = _search_in_control(desktop, query_lower, ua, max_depth=6)
        if result:
            return result

    except Exception as e:
        print(f"  [UIAuto] Error during find_element('{query}'): {e}")

    return None


def _search_in_control(root, query_lower: str, ua, depth: int = 0, max_depth: int = 6) -> dict | None:
    """Recursive DFS through the UI tree searching for a name match."""
    if depth > max_depth:
        return None

    try:
        name = root.Name.strip() if root.Name else ""
        ctrl_type = root.ControlTypeName if hasattr(root, "ControlTypeName") else ""

        # Check if this control matches
        is_interactive = ctrl_type in _INTERACTIVE_TYPES
        is_structural = ctrl_type in _STRUCTURAL_TYPES
        if name and query_lower in name.lower() and (is_interactive or is_structural):
            rect = root.BoundingRectangle
            if rect and rect.width() > 0 and rect.height() > 0:
                return {
                    "name":         name,
                    "control_type": ctrl_type,
                    "bbox":         [rect.left, rect.top, rect.right, rect.bottom],
                    "pid":          root.ProcessId,
                    "source":       "ui_automation",
                    "is_interactive": is_interactive,
                }
    except Exception:
        pass

    # Recurse into children
    try:
        for child in root.GetChildren():
            result = _search_in_control(child, query_lower, ua, depth + 1, max_depth)
            if result:
                return result
    except Exception:
        pass

    return None


# ─── Control Tree ─────────────────────────────────────────────────────────────

def get_all_controls(window_title_keyword: str = None) -> list[dict]:
    """
    Returns a flat list of all named interactive controls, optionally
    scoped to a window whose title contains `window_title_keyword`.

    Useful for letting PANDA understand *all* clickable things on screen.
    Each entry: {"name": str, "control_type": str, "bbox": [...], "pid": int}
    """
    ua = _get_ua()
    if ua is None:
        return []

    results = []
    try:
        desktop = ua.GetRootControl()

        if window_title_keyword:
            # Scope to a specific window
            kw = window_title_keyword.lower()
            for win in desktop.GetChildren():
                if kw in (win.Name or "").lower():
                    _collect_controls(win, results, ua, max_depth=5)
                    break
        else:
            # All top-level windows
            for win in desktop.GetChildren():
                _collect_controls(win, results, ua, max_depth=4)

    except Exception as e:
        print(f"  [UIAuto] Error in get_all_controls: {e}")

    return results


def _collect_controls(root, out: list, ua, depth: int = 0, max_depth: int = 4):
    """DFS collector — appends interactive, named controls to `out`."""
    if depth > max_depth:
        return
    try:
        name = root.Name.strip() if root.Name else ""
        ctrl_type = root.ControlTypeName if hasattr(root, "ControlTypeName") else ""
        is_interactive = ctrl_type in _INTERACTIVE_TYPES
        is_structural = ctrl_type in _STRUCTURAL_TYPES
        if name and (is_interactive or is_structural):
            rect = root.BoundingRectangle
            if rect and rect.width() > 0:
                out.append({
                    "name":         name,
                    "control_type": ctrl_type,
                    "bbox":         [rect.left, rect.top, rect.right, rect.bottom],
                    "pid":          root.ProcessId,
                    "is_interactive": is_interactive,
                })
    except Exception:
        pass
    try:
        for child in root.GetChildren():
            _collect_controls(child, out, ua, depth + 1, max_depth)
    except Exception:
        pass
