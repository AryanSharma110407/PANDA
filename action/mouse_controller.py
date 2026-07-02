"""
PANDA — Mouse Controller (Layer 1)
====================================
Raw mouse operations using pyautogui.
Every function checks STOP_EVENT before executing.

Safety:
- pyautogui.FAILSAFE = True (move mouse to top-left corner to abort)
- All coordinates clamped to screen bounds
- Minimum 0.1s pause between actions
"""

import time

try:
    # pyrefly: ignore [missing-import]
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1  # minimum delay between pyautogui actions
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("  \033[33m[MouseController] pyautogui not installed. Run: pip install pyautogui\033[0m")


def _check_available():
    if not PYAUTOGUI_AVAILABLE:
        raise RuntimeError("[MouseController] pyautogui is not installed.")


def _check_stop():
    """Check the global STOP_EVENT from action_executor."""
    from action.action_executor import STOP_EVENT
    if STOP_EVENT.is_set():
        raise RuntimeError("[MouseController] Action halted by STOP_EVENT.")


def _phys_to_logical_virtual(x_rel: int, y_rel: int) -> tuple[int, int]:
    """
    Converts active-monitor-relative physical coordinates (pixels) to logical virtual screen coordinates (points).
    """
    try:
        import win32gui
        import win32api
        import win32con
        import ctypes
        
        hwnd = win32gui.GetForegroundWindow()
        monitor_phys_left = 0
        monitor_phys_top = 0
        scale_factor = 1.0
        
        if hwnd:
            hmonitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            if hmonitor:
                minfo = win32api.GetMonitorInfo(hmonitor)
                rect = minfo["Monitor"]  # (left, top, right, bottom)
                monitor_phys_left = rect[0]
                monitor_phys_top = rect[1]
                
            try:
                dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
                scale_factor = dpi / 96.0
            except AttributeError:
                try:
                    dpi = ctypes.windll.user32.GetDpiForSystem()
                    scale_factor = dpi / 96.0
                except Exception:
                    pass
                    
        abs_phys_x = monitor_phys_left + x_rel
        abs_phys_y = monitor_phys_top + y_rel
        
        logical_x = int(abs_phys_x / scale_factor)
        logical_y = int(abs_phys_y / scale_factor)
        
        return logical_x, logical_y
    except Exception:
        return x_rel, y_rel

def _clamp_coords(x: int, y: int) -> tuple[int, int]:
    """Clamp coordinates to virtual screen bounds."""
    _check_available()
    logical_x, logical_y = _phys_to_logical_virtual(x, y)
    
    try:
        import win32api
        import win32con
        virtual_w = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
        virtual_h = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
        virtual_x = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        virtual_y = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        
        logical_x = max(virtual_x, min(logical_x, virtual_x + virtual_w - 1))
        logical_y = max(virtual_y, min(logical_y, virtual_y + virtual_h - 1))
    except Exception:
        screen_w, screen_h = pyautogui.size()
        logical_x = max(0, min(logical_x, screen_w - 1))
        logical_y = max(0, min(logical_y, screen_h - 1))
        
    return logical_x, logical_y


def wait_for_user_idle(idle_time_seconds: float = 10.0):
    """
    Blocks until the mouse has been completely still for `idle_time_seconds`.
    This prevents PANDA from fighting the user for control of the mouse.
    """
    if not PYAUTOGUI_AVAILABLE:
        return
        
    while True:
        pos1 = pyautogui.position()
        time.sleep(0.2)
        pos2 = pyautogui.position()
        
        if pos1 != pos2:
            print(f"  \033[33m[PANDA] [WARN] External mouse movement detected. Pausing until still for {idle_time_seconds}s...\033[0m", flush=True)
            still_time = 0.0
            while still_time < idle_time_seconds:
                p1 = pyautogui.position()
                time.sleep(0.5)
                p2 = pyautogui.position()
                if p1 != p2:
                    still_time = 0.0 # Reset timer
                else:
                    still_time += 0.5
            print("  \033[32m[PANDA] [OK] Mouse is still. Resuming task.\033[0m", flush=True)
            break
        else:
            break


def move_to(x: int, y: int, duration: float = 0.3) -> dict:
    """Smoothly move mouse to (x, y)."""
    _check_available()
    _check_stop()
    wait_for_user_idle(0.5)
    x, y = _clamp_coords(x, y)
    pyautogui.moveTo(x, y, duration=duration)
    return {"success": True, "action": "move_to", "coords": (x, y)}


def click(x: int, y: int) -> dict:
    """Left-click at (x, y) with smooth movement."""
    _check_available()
    _check_stop()
    x, y = _clamp_coords(x, y)
    move_to(x, y, duration=0.75)  # Smoothly move first
    pyautogui.click()
    return {"success": True, "action": "click", "coords": (x, y)}


def right_click(x: int, y: int) -> dict:
    """Right-click at (x, y) with smooth movement."""
    _check_available()
    _check_stop()
    x, y = _clamp_coords(x, y)
    move_to(x, y, duration=0.75)
    pyautogui.rightClick()
    return {"success": True, "action": "right_click", "coords": (x, y)}


def double_click(x: int, y: int) -> dict:
    """Double-click at (x, y) with smooth movement."""
    _check_available()
    _check_stop()
    x, y = _clamp_coords(x, y)
    move_to(x, y, duration=0.75)
    pyautogui.doubleClick()
    return {"success": True, "action": "double_click", "coords": (x, y)}


def scroll(x: int, y: int, clicks: int) -> dict:
    """
    Scroll at position (x, y).
    clicks > 0 = scroll up, clicks < 0 = scroll down.
    """
    _check_available()
    _check_stop()
    wait_for_user_idle(0.5)
    x, y = _clamp_coords(x, y)
    pyautogui.moveTo(x, y, duration=0.1)
    pyautogui.scroll(clicks)
    return {"success": True, "action": "scroll", "coords": (x, y), "clicks": clicks}


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> dict:
    """Click-drag from (x1, y1) to (x2, y2)."""
    _check_available()
    _check_stop()
    wait_for_user_idle(0.5)
    x1, y1 = _clamp_coords(x1, y1)
    x2, y2 = _clamp_coords(x2, y2)
    pyautogui.moveTo(x1, y1, duration=0.1)
    _check_stop()  # check again before the drag
    pyautogui.mouseDown()
    pyautogui.moveTo(x2, y2, duration=duration)
    pyautogui.mouseUp()
    return {"success": True, "action": "drag", "from": (x1, y1), "to": (x2, y2)}


def get_position() -> tuple[int, int]:
    """Returns current mouse position."""
    _check_available()
    pos = pyautogui.position()
    return (pos.x, pos.y)


def get_screen_size() -> tuple[int, int]:
    """Returns screen dimensions (width, height)."""
    _check_available()
    size = pyautogui.size()
    return (size.width, size.height)
