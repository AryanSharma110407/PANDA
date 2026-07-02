"""
PANDA — Keyboard Controller (Layer 2)
=======================================
Raw keyboard operations using pyautogui.
Every function checks STOP_EVENT before executing.
"""

try:
    # pyrefly: ignore [missing-import]
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


def _check_available():
    if not PYAUTOGUI_AVAILABLE:
        raise RuntimeError("[KeyboardController] pyautogui is not installed.")


def _check_stop():
    """Check the global STOP_EVENT from action_executor."""
    from action.action_executor import STOP_EVENT
    if STOP_EVENT.is_set():
        raise RuntimeError("[KeyboardController] Action halted by STOP_EVENT.")


# ── Supported key names ─────────────────────────────────────────────────────
# pyautogui supports these natively; we list them for reference and validation.
SUPPORTED_KEYS = {
    # Navigation
    "enter", "return", "tab", "escape", "esc", "backspace", "delete", "del",
    "space", "home", "end", "pageup", "pagedown",
    "up", "down", "left", "right",
    # Modifiers
    "ctrl", "alt", "shift", "win", "command",
    # Function keys
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    # Special
    "capslock", "numlock", "scrolllock", "printscreen",
    "insert", "pause", "volumeup", "volumedown", "volumemute",
}

# Common aliases
KEY_ALIASES = {
    "return": "enter",
    "esc": "escape",
    "del": "delete",
    "command": "win",
    "windows": "win",
}


def _normalize_key(key: str) -> str:
    """Normalize a key name to pyautogui's expected format."""
    key = key.lower().strip()
    return KEY_ALIASES.get(key, key)


def type_text(text: str, interval: float = 0.04) -> dict:
    """
    Type text at human-like speed.
    interval = seconds between each keystroke.
    Supports Unicode characters by pasting via clipboard if non-ASCII text is present.
    """
    _check_available()
    _check_stop()
    import time
    
    is_ascii = all(ord(c) < 128 for c in text)
    if is_ascii:
        pyautogui.typewrite(text, interval=interval)
    else:
        import tkinter as tk
        old_clip = ""
        try:
            root = tk.Tk()
            root.withdraw()
            old_clip = root.clipboard_get()
            root.destroy()
        except Exception:
            pass
            
        try:
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
        except Exception:
            pass
            
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        
        if old_clip:
            try:
                root = tk.Tk()
                root.withdraw()
                root.clipboard_clear()
                root.clipboard_append(old_clip)
                root.update()
                root.destroy()
            except Exception:
                pass
                
    return {"success": True, "action": "type_text", "text": text, "length": len(text)}


def press_key(key: str) -> dict:
    """Press a single key (e.g. 'enter', 'escape', 'f5')."""
    _check_available()
    _check_stop()
    normalized = _normalize_key(key)
    pyautogui.press(normalized)
    return {"success": True, "action": "press_key", "key": normalized}


def hotkey(*keys: str) -> dict:
    """
    Press a key combination (e.g. hotkey('ctrl', 'c') for copy).
    """
    _check_available()
    _check_stop()
    normalized = [_normalize_key(k) for k in keys]
    pyautogui.hotkey(*normalized)
    return {"success": True, "action": "hotkey", "keys": normalized}


def hold_key(key: str, duration: float = 0.5) -> dict:
    """Hold a key down for a specified duration."""
    import time
    _check_available()
    _check_stop()
    normalized = _normalize_key(key)
    pyautogui.keyDown(normalized)
    time.sleep(duration)
    _check_stop()
    pyautogui.keyUp(normalized)
    return {"success": True, "action": "hold_key", "key": normalized, "duration": duration}


def clear_and_type(text: str, interval: float = 0.04) -> dict:
    """Select all existing text (Ctrl+A), delete it, then type new text."""
    _check_available()
    _check_stop()
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("delete")
    _check_stop()
    type_text(text, interval=interval)
    return {"success": True, "action": "clear_and_type", "text": text}


def parse_and_execute(key_string: str) -> dict:
    """
    Parse a key string like 'ctrl+c', 'alt+f4', 'enter' and execute it.
    Handles both single keys and combos with '+' separator.
    """
    _check_available()
    _check_stop()
    parts = [p.strip() for p in key_string.lower().split("+")]
    if len(parts) == 1:
        return press_key(parts[0])
    else:
        return hotkey(*parts)
