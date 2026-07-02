import os
from datetime import datetime
# pyrefly: ignore [missing-import]
import mss
# pyrefly: ignore [missing-import]
from PIL import Image

def get_active_monitor_rect() -> dict | None:
    """
    Finds the active window and returns the mss monitor dictionary of the monitor it resides on.
    """
    try:
        import win32gui
        import win32api
        import win32con
        
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            hmonitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            if hmonitor:
                minfo = win32api.GetMonitorInfo(hmonitor)
                rect = minfo["Monitor"]  # (left, top, right, bottom)
                left, top, right, bottom = rect
                return {"left": left, "top": top, "width": right - left, "height": bottom - top}
    except Exception:
        pass
    return None

def capture_screen() -> Image.Image:
    """Captures the monitor containing the active window (or primary as fallback) and returns a PIL Image."""
    with mss.mss() as sct:
        monitor = get_active_monitor_rect()
        if not monitor:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        sct_img = sct.grab(monitor)
        # Convert mss BGRA bytes to PIL RGB Image
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        return img

def capture_region(x: int, y: int, w: int, h: int) -> Image.Image:
    """Captures a specific rectangular region of the screen and returns a PIL Image."""
    with mss.mss() as sct:
        monitor = {"top": y, "left": x, "width": w, "height": h}
        sct_img = sct.grab(monitor)
        # Convert mss BGRA bytes to PIL RGB Image
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        return img

def _prune_old_screenshots(screenshots_dir: str, max_keep: int = 20):
    """Deletes old debug screenshots so the directory doesn't grow indefinitely."""
    try:
        files = [
            os.path.join(screenshots_dir, f)
            for f in os.listdir(screenshots_dir)
            if f.startswith("debug_") and f.endswith(".png")
        ]
        # Sort files by modification time (oldest first)
        files.sort(key=os.path.getmtime)
        if len(files) > max_keep:
            files_to_delete = files[:-max_keep]
            for f in files_to_delete:
                try:
                    os.remove(f)
                except Exception:
                    pass
    except Exception:
        pass

def save_debug_screenshot(tag: str) -> str:
    """Captures the screen and saves it as a debug file inside the screenshots/ directory. Returns the filepath."""
    _HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    screenshots_dir = os.path.join(_HERE, "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    
    img = capture_screen()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    # Clean the tag for safety in filenames
    clean_tag = "".join(c for c in tag if c.isalnum() or c in ("-", "_")).rstrip()
    if not clean_tag:
        clean_tag = "obs"
    filename = f"debug_{clean_tag}_{timestamp}.png"
    filepath = os.path.join(screenshots_dir, filename)
    img.save(filepath)
    
    # Prune old screenshots to save disk space
    _prune_old_screenshots(screenshots_dir, max_keep=20)
    
    return filepath
