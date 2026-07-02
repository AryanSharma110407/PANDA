"""
PANDA — Action Verifier (Sprint 8)
==================================
Verifies whether an executed action caused the screen to change or
if the expected window is currently active.
"""

from vision.screen_state import build_screen_state

def verify_screen_changed(before_state: dict) -> dict:
    """
    Captures the current screen state and compares it with the before_state.
    
    Returns:
      dict: {
        "changed": bool,
        "window_changed": bool,
        "new_summary": str
      }
    """
    session_id = before_state.get("session_id", "default")
    new_state = build_screen_state(session_id)
    
    # 1. Check if active window title changed
    before_window = before_state.get("active_window", "")
    new_window = new_state.get("active_window", "")
    window_changed = before_window != new_window
    
    # 2. Check if the frame hash changed (visual structure change)
    before_hash = before_state.get("frame_hash")
    new_hash = new_state.get("frame_hash")
    hash_changed = False
    if before_hash and new_hash:
        hash_changed = before_hash != new_hash
        
    # 3. Check if visible text (OCR results) changed
    before_texts = {t.get("text", "").strip() for t in before_state.get("visible_text", []) if t.get("text")}
    new_texts = {t.get("text", "").strip() for t in new_state.get("visible_text", []) if t.get("text")}
    
    # Remove empty strings
    before_texts.discard("")
    new_texts.discard("")
    text_changed = before_texts != new_texts
    
    # Screen is changed if either window changed, OCR texts changed, or visual hash changed
    changed = window_changed or hash_changed or text_changed
    
    return {
        "changed": changed,
        "window_changed": window_changed,
        "new_summary": new_state.get("summary", "")
    }

def verify_window_changed(target_title: str) -> bool:
    """
    Checks if the active window title contains target_title.
    """
    active_title = ""
    try:
        # pyrefly: ignore [missing-import]
        import pygetwindow as gw
        win = gw.getActiveWindow()
        if win and win.title:
            active_title = win.title
    except Exception:
        pass
        
    if not active_title:
        try:
            from vision import ui_automation_engine
            if ui_automation_engine.is_available():
                focused = ui_automation_engine.get_focused_window()
                if focused and focused.get("title"):
                    active_title = focused["title"]
        except Exception:
            pass
            
    return target_title.lower() in active_title.lower() if active_title else False
