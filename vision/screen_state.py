"""
PANDA Vision — Screen State Builder
=====================================
Builds a structured snapshot of the current screen using all 3 layers:

  Layer 1: Windows UI Automation  → active window title, named controls
  Layer 2: PaddleOCR              → all visible text with bounding boxes
  Layer 3: OpenCV                 → structural analysis (buttons, text zones, panels)

The result is a flat dict consumed by vision_tools.py to build responses
and saved to memory_manager as a screen observation.

Built by Aryan — PANDA Vision Sprint 7+
"""

from datetime import datetime
from .screenshot_manager import capture_screen
from .ocr_engine import read_image
from .opencv_engine import find_buttons, find_text_regions, find_windows
from . import ui_automation_engine

# pygetwindow is used as a lightweight Layer 1 fallback for active window title.
# It's optional — if missing, we rely on uiautomation alone.
try:
    import pygetwindow as gw  # pyrefly: ignore [missing-import]
    _GW_AVAILABLE = True
except Exception:
    gw = None
    _GW_AVAILABLE = False


def build_screen_state(session_id: str, parent_observation_id: int | None = None, pre_captured_image = None) -> dict:
    """
    Captures the current screen and runs all 3 vision layers to produce
    a structured representation of the current environment.

    Returns:
      {
        "timestamp":            str,
        "session_id":           str,
        "parent_observation_id":int | None,
        "active_window":        str,       # Layer 1 primary, pygetwindow fallback
        "ui_controls":          list[str], # Layer 1 — named interactive controls
        "visible_text":         list[dict],# Layer 2 — OCR results
        "detected_elements":    list[dict],# Layer 3 — OpenCV structural elements
        "summary":              str,       # Human-readable one-liner
        "frame_hash":           str | None # 16x16 perceptual hash of the screenshot
      }
    """
    timestamp = datetime.now().isoformat()

    # ── Layer 1: Windows UI Automation ────────────────────────────────────────
    active_window = "Unknown"
    ui_controls   = []

    try:
        if ui_automation_engine.is_available():
            focused = ui_automation_engine.get_focused_window()
            if focused and focused.get("title"):
                active_window = focused["title"]

            # Grab named controls from the active window (capped for performance)
            controls = ui_automation_engine.get_all_controls(
                window_title_keyword=active_window if active_window != "Unknown" else None
            )
            ui_controls = [c["name"] for c in controls if c.get("name")][:20]
    except Exception as ua_err:
        print(f"  [ScreenState] Layer 1 (UIAuto) error: {ua_err}")

    # Fallback: pygetwindow (if Layer 1 returned nothing)
    if active_window == "Unknown" and _GW_AVAILABLE:
        try:
            win = gw.getActiveWindow()
            if win and win.title:
                active_window = win.title.strip()
        except Exception as gw_err:
            print(f"  [ScreenState] pygetwindow fallback error: {gw_err}")

    # ── Layer 2: OCR ──────────────────────────────────────────────────────────
    visible_text = []
    frame_hash = None
    try:
        image = pre_captured_image if pre_captured_image is not None else capture_screen()
        frame_hash = image.resize((16, 16)).convert("L").tobytes().hex()
        visible_text = read_image(image)
    except Exception as ocr_err:
        print(f"  [ScreenState] Layer 2 (OCR) error: {ocr_err}")
        image = None

    # ── Layer 3: OpenCV structural analysis ───────────────────────────────────
    detected_elements = []
    if image is not None:
        try:
            detected_elements.extend(find_buttons(image))
            detected_elements.extend(find_text_regions(image))
            detected_elements.extend(find_windows(image))
        except Exception as cv_err:
            print(f"  [ScreenState] Layer 3 (OpenCV) error: {cv_err}")

    # ── Summary ───────────────────────────────────────────────────────────────
    seen_texts = set()
    top_texts  = []
    for t in sorted(visible_text, key=lambda x: x.get("confidence", 0), reverse=True):
        txt = t["text"].strip()
        if txt and txt not in seen_texts:
            seen_texts.add(txt)
            top_texts.append(txt)
            if len(top_texts) >= 5:
                break

    summary = f"Active Window: '{active_window}'."
    if top_texts:
        summary += f" Visible text: {', '.join(top_texts)}."
    else:
        summary += " No text detected."
    if ui_controls:
        summary += f" UI controls: {', '.join(ui_controls[:3])}."

    return {
        "timestamp":            timestamp,
        "session_id":           session_id,
        "parent_observation_id":parent_observation_id,
        "active_window":        active_window,
        "ui_controls":          ui_controls,
        "visible_text":         visible_text,
        "detected_elements":    detected_elements,
        "summary":              summary,
        "frame_hash":           frame_hash,
    }
