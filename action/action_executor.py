"""
PANDA — Action Executor (Layer 3)
===================================
High-level named actions that combine vision (Sprint 7) + mouse/keyboard (Layers 1-2).
Contains the global STOP_EVENT for halting actions mid-execution.

Click targeting priority:
  1. Element Name (template matching via OpenCV)
  2. OCR Text (fuzzy match on screen text)
  3. Raw Coordinates (fallback)
"""

import threading
import time

from action import mouse_controller, keyboard_controller

# ── Global Stop Control ──────────────────────────────────────────────────────
STOP_EVENT = threading.Event()
UNDO_STACK = []

# ── Destructive Action Keywords ──────────────────────────────────────────────
DESTRUCTIVE_KEYWORDS = [
    "delete", "remove", "send", "submit", "pay", "purchase", "transfer",
    "confirm", "post", "publish", "execute", "drop", "format", "erase",
    "uninstall", "checkout", "order", "sign out", "log out", "terminate"
]


def is_destructive(action_type: str, params: dict) -> bool:
    """
    Classifies an action as destructive based on keyword matching.
    Destructive actions trigger HITL (Human-in-the-Loop) gatekeeping
    before execution.
    
    Returns True if the action or its parameters contain destructive keywords.
    """
    action_str = str(action_type).lower() if action_type else ""
    combined = action_str + " " + " ".join(str(v) for v in params.values()).lower()
    
    for keyword in DESTRUCTIVE_KEYWORDS:
        if keyword in combined:
            return True
    return False


def kill_active_app() -> dict:
    """
    Home Base Reset: Forcefully terminates the currently active application.
    
    Used when the agent is stuck in an unrecoverable UI state after
    exhausting retry attempts on a milestone. Kills the foreground
    application so the milestone can be restarted from a clean slate.
    
    Strategy:
      1. Try Alt+F4 (graceful close)
      2. If that fails, identify the foreground process and taskkill it
    """
    import subprocess
    
    result_details = []
    
    try:
        # Step 1: Try Alt+F4 (graceful close)
        from action import keyboard_controller
        keyboard_controller.hotkey('alt', 'F4')
        time.sleep(1.0)
        result_details.append("Sent Alt+F4 to active window.")
    except Exception as e:
        result_details.append(f"Alt+F4 failed: {e}")
    
    try:
        # Step 2: Identify and kill the foreground process using PowerShell
        # Get the PID of the foreground window
        ps_script = (
            "Add-Type @'\n"
            "using System;\n"
            "using System.Runtime.InteropServices;\n"
            "public class WinAPI {\n"
            "    [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();\n"
            "    [DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);\n"
            "}\n"
            "'@\n"
            "$hwnd = [WinAPI]::GetForegroundWindow()\n"
            "$pid = 0\n"
            "[WinAPI]::GetWindowThreadProcessId($hwnd, [ref]$pid) | Out-Null\n"
            "Write-Output $pid"
        )
        proc = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=5
        )
        pid_str = proc.stdout.strip()
        
        if pid_str and pid_str.isdigit():
            pid = int(pid_str)
            # Don't kill explorer.exe (the desktop shell)
            check = subprocess.run(
                ["powershell", "-Command", f"(Get-Process -Id {pid}).ProcessName"],
                capture_output=True, text=True, timeout=3
            )
            proc_name = check.stdout.strip().lower()
            
            if proc_name in ("explorer", "dwm", "csrss", "svchost", "system"):
                result_details.append(f"Skipped killing system process '{proc_name}' (PID {pid}).")
            else:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], timeout=5)
                result_details.append(f"Killed process '{proc_name}' (PID {pid}).")
        else:
            result_details.append("Could not identify foreground process PID.")
            
    except subprocess.TimeoutExpired:
        result_details.append("Process kill timed out.")
    except Exception as e:
        result_details.append(f"Process kill failed: {e}")
    
    return _make_result(True, "kill_active_app", " | ".join(result_details))


def stop_all_actions():
    """Call this from voice 'stop' command or any interrupt."""
    STOP_EVENT.set()
    print("  \033[31m[ActionExecutor] ⛔ STOP_EVENT fired — all actions halted.\033[0m")


def reset_stop():
    """Reset after stop — ready for next action."""
    STOP_EVENT.clear()


class ActionHaltedError(RuntimeError):
    pass

def _check_stop():
    """Raises ActionHaltedError if STOP_EVENT is set."""
    if STOP_EVENT.is_set():
        raise ActionHaltedError("[ActionExecutor] Action halted by STOP_EVENT.")


def _make_result(success: bool, action: str, details: str,
                 coords: tuple | None = None, error: str | None = None) -> dict:
    """Standard result dict returned by all executor functions."""
    return {
        "success": success,
        "action": action,
        "details": details,
        "coords": coords,
        "error": error,
    }


# ── Click Actions ────────────────────────────────────────────────────────────


def click_text_on_screen(text: str) -> dict:
    """
    Priority 2 — Find text on screen via OCR, then click its center.
    Uses fuzzy matching (case-insensitive substring match).
    """
    _check_stop()
    try:
        from vision.ocr_engine import read_screen

        ocr_results = read_screen()
        if not ocr_results:
            return _make_result(False, "click_text", "OCR returned no text on screen.",
                                error="No text detected")

        # Find best matching OCR result (case-insensitive substring)
        text_lower = text.lower().strip()
        best_match = None
        best_confidence = 0.0

        for item in ocr_results:
            if text_lower in item["text"].lower():
                if item["confidence"] > best_confidence:
                    best_match = item
                    best_confidence = item["confidence"]

        if not best_match:
            return _make_result(False, "click_text",
                                f"Could not find text '{text}' on screen.",
                                error="Text not found on screen")

        _check_stop()
        # Click center of bounding box
        bbox = best_match["bbox"]  # [x_min, y_min, x_max, y_max]
        cx = int((bbox[0] + bbox[2]) / 2)
        cy = int((bbox[1] + bbox[3]) / 2)
        mouse_controller.click(cx, cy)

        return _make_result(True, "click_text",
                            f"Clicked text '{best_match['text']}' at ({cx}, {cy}).",
                            coords=(cx, cy))
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "click_text", str(e), error=str(e))


def click_ui_automation(text: str) -> dict:
    """
    Priority 2.5 — Find text in the UI Automation tree.
    """
    _check_stop()
    try:
        from vision.ui_automation_engine import find_element
        
        element = find_element(text)
        if not element:
            return _make_result(False, "click_ui_automation", f"UI Automation returned no element for '{text}'.",
                                error="Element not found in UI tree")

        _check_stop()
        # Click center of bounding box
        bbox = element["bbox"]  # [x_min, y_min, x_max, y_max]
        cx = int((bbox[0] + bbox[2]) / 2)
        cy = int((bbox[1] + bbox[3]) / 2)
        mouse_controller.click(cx, cy)

        return _make_result(True, "click_ui_automation",
                            f"Clicked UI element '{element['name']}' at ({cx}, {cy}).",
                            coords=(cx, cy))
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "click_ui_automation", str(e), error=str(e))


def click_at(x: int, y: int) -> dict:
    """
    Priority 3 (fallback) — Click at raw coordinates.
    Used when LLM has coordinates from a prior 'look' observation.
    """
    _check_stop()
    try:
        mouse_controller.click(x, y)
        return _make_result(True, "click_at", f"Clicked at ({x}, {y}).", coords=(x, y))
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "click_at", str(e), error=str(e))


def smart_click(target: str) -> dict:
    """
    Tries all three click methods in priority order:
      1. Element name (template match)
      2. OCR text (screen text search)
      3. Raw coordinates (if target looks like 'x,y')
    """
    _check_stop()

    # Priority 2: Try as OCR text
    result = click_text_on_screen(target)
    if result["success"]:
        return result

    # Priority 2.5: Try UI Automation Tree (since OCR is disabled by default)
    result = click_ui_automation(target)
    if result["success"]:
        return result

    # Priority 3: Try parsing bounding boxes from UI representations (e.g. 'button, bbox: [459, 926, 610, 990]')
    import re
    match = re.search(r'bbox:\s*\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', target)
    if match:
        x1, y1, x2, y2 = map(int, match.groups())
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        return click_at(cx, cy)

    # Priority 4: Try as raw coordinates (format: "x,y")
    if "," in target:
        parts = target.split(",")
        try:
            x, y = int(parts[0].strip()), int(parts[1].strip())
            return click_at(x, y)
        except (ValueError, IndexError):
            pass

    return _make_result(False, "smart_click",
                        f"Could not find '{target}' using any method (element name, OCR text, bounding box, or coordinates).",
                        error="Target not found")


# ── Right Click Actions ───────────────────────────────────────────────────────


def right_click_text_on_screen(text: str) -> dict:
    """
    Priority 2 — Find text on screen via OCR, then right click its center.
    Uses fuzzy matching (case-insensitive substring match).
    """
    _check_stop()
    try:
        from vision.ocr_engine import read_screen

        ocr_results = read_screen()
        if not ocr_results:
            return _make_result(False, "right_click_text", "OCR returned no text on screen.",
                                error="No text detected")

        text_lower = text.lower().strip()
        best_match = None
        best_confidence = 0.0

        for item in ocr_results:
            if text_lower in item["text"].lower():
                if item["confidence"] > best_confidence:
                    best_match = item
                    best_confidence = item["confidence"]

        if not best_match:
            return _make_result(False, "right_click_text",
                                f"Could not find text '{text}' on screen.",
                                error="Text not found on screen")

        _check_stop()
        bbox = best_match["bbox"]  # [x_min, y_min, x_max, y_max]
        cx = int((bbox[0] + bbox[2]) / 2)
        cy = int((bbox[1] + bbox[3]) / 2)
        mouse_controller.right_click(cx, cy)

        return _make_result(True, "right_click_text",
                            f"Right-clicked text '{best_match['text']}' at ({cx}, {cy}).",
                            coords=(cx, cy))
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "right_click_text", str(e), error=str(e))


def right_click_ui_automation(text: str) -> dict:
    """
    Priority 2.5 — Find text in the UI Automation tree, then right click its center.
    """
    _check_stop()
    try:
        from vision.ui_automation_engine import find_element
        
        element = find_element(text)
        if not element:
            return _make_result(False, "right_click_ui_automation", f"UI Automation returned no element for '{text}'.",
                                error="Element not found in UI tree")

        _check_stop()
        bbox = element["bbox"]  # [x_min, y_min, x_max, y_max]
        cx = int((bbox[0] + bbox[2]) / 2)
        cy = int((bbox[1] + bbox[3]) / 2)
        mouse_controller.right_click(cx, cy)

        return _make_result(True, "right_click_ui_automation",
                            f"Right-clicked UI element '{element['name']}' at ({cx}, {cy}).",
                            coords=(cx, cy))
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "right_click_ui_automation", str(e), error=str(e))


def right_click_at(x: int, y: int) -> dict:
    """
    Priority 3 (fallback) — Right click at raw coordinates.
    """
    _check_stop()
    try:
        mouse_controller.right_click(x, y)
        return _make_result(True, "right_click_at", f"Right-clicked at ({x}, {y}).", coords=(x, y))
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "right_click_at", str(e), error=str(e))


def smart_right_click(target: str) -> dict:
    """
    Tries all three right click methods in priority order:
      1. Element name (template match)
      2. OCR text (screen text search)
      3. UI Automation element (accessibility tree)
      4. Bounding box coordinates (if matched in text)
      5. Raw coordinates (if target looks like 'x,y')
    """
    _check_stop()

    # Priority 2: Try as OCR text
    result = right_click_text_on_screen(target)
    if result["success"]:
        return result

    # Priority 2.5: Try UI Automation Tree
    result = right_click_ui_automation(target)
    if result["success"]:
        return result

    # Priority 3: Try parsing bounding boxes from UI representations
    import re
    match = re.search(r'bbox:\s*\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', target)
    if match:
        x1, y1, x2, y2 = map(int, match.groups())
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        return right_click_at(cx, cy)

    # Priority 4: Try as raw coordinates (format: "x,y")
    if "," in target:
        parts = target.split(",")
        try:
            x, y = int(parts[0].strip()), int(parts[1].strip())
            return right_click_at(x, y)
        except (ValueError, IndexError):
            pass

    return _make_result(False, "smart_right_click",
                        f"Could not right-click '{target}' using any method (element name, OCR text, bounding box, or coordinates).",
                        error="Target not found")


# ── Type Actions ─────────────────────────────────────────────────────────────

def type_into_focused(text: str, clear_first: bool = False) -> dict:
    """Types text into whatever field is currently focused."""
    _check_stop()
    try:
        if clear_first:
            keyboard_controller.clear_and_type(text)
        else:
            keyboard_controller.type_text(text)
        return _make_result(True, "type", f"Typed {len(text)} characters.", coords=None)
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "type", str(e), error=str(e))


def focus_and_type(element_name: str, text: str, clear_first: bool = False) -> dict:
    """Click on an element using smart_click, wait briefly, then type text."""
    _check_stop()
    click_result = smart_click(element_name)
    if not click_result["success"]:
        return _make_result(False, "focus_and_type",
                            f"Failed to click '{element_name}': {click_result.get('error', 'Unknown Error')}",
                            error=click_result.get("error", "Unknown Error"))

    time.sleep(0.25)
    _check_stop()
    return type_into_focused(text, clear_first=clear_first)


# ── Key Press Actions ────────────────────────────────────────────────────────

def press(key_or_combo: str) -> dict:
    """
    Press a key or key combo.
    Supports: 'enter', 'escape', 'ctrl+c', 'alt+f4', 'f5', etc.
    """
    _check_stop()
    try:
        result = keyboard_controller.parse_and_execute(key_or_combo)
        return _make_result(True, "press", f"Pressed '{key_or_combo}'.")
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "press", str(e), error=str(e))


# ── Scroll Actions ───────────────────────────────────────────────────────────

def scroll_at(direction: str, amount: int = 3) -> dict:
    """
    Scroll at current mouse position.
    direction: 'up', 'down', 'left', 'right'
    """
    _check_stop()
    try:
        current_x, current_y = mouse_controller.get_position()

        if direction.lower() in ("up",):
            clicks = amount
        elif direction.lower() in ("down",):
            clicks = -amount
        else:
            return _make_result(False, "scroll",
                                f"Unsupported scroll direction: '{direction}'",
                                error="Use 'up' or 'down'")

        mouse_controller.scroll(current_x, current_y, clicks)
        return _make_result(True, "scroll",
                            f"Scrolled {direction} by {amount} clicks.",
                            coords=(current_x, current_y))
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "scroll", str(e), error=str(e))


# ── Drag Actions ─────────────────────────────────────────────────────────────

def drag_between(source: str, target: str, duration: float = 0.5) -> dict:
    """
    Drag from source to target.
    Both can be element names or 'x,y' coordinates.
    """
    _check_stop()

    def _resolve_position(name_or_coords: str) -> tuple[int, int] | None:
        """Try to resolve a string to (x, y) coordinates."""
        # Try as OCR text
        try:
            from vision.ocr_engine import read_screen
            ocr_results = read_screen()
            if ocr_results:
                text_lower = name_or_coords.lower().strip()
                best_match = None
                best_confidence = 0.0
                for item in ocr_results:
                    if text_lower in item["text"].lower() and item["confidence"] > best_confidence:
                        best_match = item
                        best_confidence = item["confidence"]
                if best_match:
                    return (best_match["x"], best_match["y"])
        except Exception:
            pass

        # Try as coordinates
        if "," in name_or_coords:
            parts = name_or_coords.split(",")
            try:
                return (int(parts[0].strip()), int(parts[1].strip()))
            except (ValueError, IndexError):
                pass
        return None

    try:
        src_pos = _resolve_position(source)
        if not src_pos:
            return _make_result(False, "drag", f"Could not resolve source: '{source}'",
                                error="Source not found")

        _check_stop()
        tgt_pos = _resolve_position(target)
        if not tgt_pos:
            return _make_result(False, "drag", f"Could not resolve target: '{target}'",
                                error="Target not found")

        _check_stop()
        mouse_controller.drag(src_pos[0], src_pos[1], tgt_pos[0], tgt_pos[1], duration=duration)
        return _make_result(True, "drag",
                            f"Dragged from {src_pos} to {tgt_pos}.",
                            coords=tgt_pos)
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "drag", str(e), error=str(e))


def select_and_copy(target: str) -> dict:
    """
    Select all text (Ctrl+A) and copy (Ctrl+C) from a target element.
    First, it clicks the target using smart_click logic to focus it.
    Then, it sends Ctrl+A and Ctrl+C.
    Finally, it reads the clipboard via pyperclip and returns it.
    """
    _check_stop()
    try:
        import pyperclip
        # Clear clipboard first to avoid stale data
        pyperclip.copy("")
        
        # Click target using smart_click
        click_res = smart_click(target)
        if not click_res["success"]:
            return _make_result(False, "select_and_copy", f"Could not click target: '{target}'",
                                error=click_res.get("error", "Target click failed"))
        
        _check_stop()
        time.sleep(0.3)  # Small delay to let focus settle
        
        # Press Ctrl+A
        keyboard_controller.hotkey('ctrl', 'a')
        _check_stop()
        time.sleep(0.2)
        
        # Press Ctrl+C
        keyboard_controller.hotkey('ctrl', 'c')
        _check_stop()
        time.sleep(0.3)  # Give Windows clipboard a moment to update
        
        text = pyperclip.paste().strip()
        if not text:
            return _make_result(False, "select_and_copy", "Clipboard was empty after copy.",
                                error="No text copied")
            
        return _make_result(True, "select_and_copy", text,
                            coords=click_res.get("coords"))
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "select_and_copy", str(e), error=str(e))


def undo() -> dict:
    """Undoes the last click or type action to recover from mistakes."""
    if not UNDO_STACK:
        return _make_result(False, "undo", "No actions to undo.")
        
    action_type, data = UNDO_STACK.pop()
    try:
        if action_type == "click":
            # Restore window focus
            prev_win = data.get("prev_win")
            if prev_win:
                try:
                    if prev_win.isMinimized:
                        prev_win.restore()
                    prev_win.activate()
                except Exception:
                    pass
            # Restore mouse position
            prev_pos = data.get("prev_pos")
            if prev_pos:
                try:
                    mouse_controller.move_to(prev_pos[0], prev_pos[1], duration=0.2)
                except Exception:
                    pass
            return _make_result(True, "undo", "Undid last click (restored window focus and mouse position).")
            
        elif action_type == "type":
            length = data.get("length", 0)
            if length > 0:
                try:
                    for _ in range(length):
                        keyboard_controller.press_key("backspace")
                except Exception:
                    pass
                return _make_result(True, "undo", f"Undid last type (sent {length} Backspaces).")
    except ActionHaltedError:
        raise
    except Exception as e:
        return _make_result(False, "undo", f"Failed to undo: {e}", error=str(e))
        
    return _make_result(False, "undo", "Unknown action type in undo stack.")
