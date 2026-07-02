"""
PANDA — Action Tools (Layer 5)
================================
LLM-callable handler functions wired into alya.py's dispatch table.
Same pattern as vision_tools.py — each handler takes (target/text, session_id)
and returns a speech-ready response string.

Every handler: reset stop → capture before state → execute → verify → log → respond.
"""

from action import action_executor, action_verifier


def _capture_before_state(session_id: str) -> dict:
    """Capture the current screen state for later verification."""
    try:
        from vision.screen_state import build_screen_state
        return build_screen_state(session_id)
    except Exception as e:
        print(f"  [ActionTools] Could not capture before-state: {e}")
        return {"session_id": session_id, "active_window": "", "summary": "", "visible_text": []}


def _log_action(session_id: str, action_type: str, target: str,
                coords_x: int | None, coords_y: int | None,
                success: bool, verified: bool, error_msg: str | None = None):
    """Log action to the action_log table in the database."""
    try:
        import memory_manager
        memory_manager.log_action(
            session_id=session_id,
            action_type=action_type,
            target=target,
            coords_x=coords_x,
            coords_y=coords_y,
            success=success,
            verified=verified,
            error_msg=error_msg
        )
    except Exception as e:
        print(f"  [ActionTools] Could not log action: {e}")


# ── Click ────────────────────────────────────────────────────────────────────

def handle_click(target: str, session_id: str) -> str:
    """
    Click a target using smart_click priority:
      Element Name → OCR Text → Coordinates
    """
    action_executor.reset_stop()
    before = _capture_before_state(session_id)

    result = action_executor.smart_click(target)

    # Verify
    verified = False
    verify_info = ""
    if result["success"]:
        verification = action_verifier.verify_screen_changed(before)
        verified = verification.get("changed", False)
        if verified:
            verify_info = f" The screen changed — {verification.get('new_summary', 'action appears to have worked')}."
        else:
            verify_info = " The screen didn't visibly change."

    # Log
    coords = result.get("coords")
    _log_action(session_id, "click", target,
                coords[0] if coords else None,
                coords[1] if coords else None,
                result["success"], verified,
                result.get("error"))

    if result["success"]:
        return f"I clicked '{target}' at {result['coords']}.{verify_info}"
    else:
        return f"I couldn't click '{target}'. {result.get('error', 'Unknown error')}."


# ── Right Click ──────────────────────────────────────────────────────────────

def handle_right_click(target: str, session_id: str) -> str:
    """
    Right click a target using smart_right_click priority:
      Element Name → OCR Text → UI Automation → Coordinates
    """
    action_executor.reset_stop()
    before = _capture_before_state(session_id)

    result = action_executor.smart_right_click(target)

    # Verify
    verified = False
    verify_info = ""
    if result["success"]:
        verification = action_verifier.verify_screen_changed(before)
        verified = verification.get("changed", False)
        if verified:
            verify_info = f" The screen changed — {verification.get('new_summary', 'action appears to have worked')}."
        else:
            verify_info = " The screen didn't visibly change."

    # Log
    coords = result.get("coords")
    _log_action(session_id, "right_click", target,
                coords[0] if coords else None,
                coords[1] if coords else None,
                result["success"], verified,
                result.get("error"))

    if result["success"]:
        return f"I right-clicked '{target}' at {result['coords']}.{verify_info}"
    else:
        return f"I couldn't right-click '{target}'. {result.get('error', 'Unknown error')}."


# ── Type ─────────────────────────────────────────────────────────────────────

def handle_type(text: str, session_id: str) -> str:
    """Type text into the currently focused field."""
    action_executor.reset_stop()

    result = action_executor.type_into_focused(text)

    _log_action(session_id, "type", text[:50], None, None,
                result["success"], False, result.get("error"))

    if result["success"]:
        return f"I typed '{text[:40]}{'...' if len(text) > 40 else ''}'."
    else:
        return f"I couldn't type the text. {result.get('error', 'Unknown error')}."


# ── Press ────────────────────────────────────────────────────────────────────

def handle_press(key: str, session_id: str) -> str:
    """Press a key or key combination (e.g. 'enter', 'ctrl+c', 'alt+f4')."""
    action_executor.reset_stop()

    result = action_executor.press(key)

    _log_action(session_id, "press", key, None, None,
                result["success"], False, result.get("error"))

    if result["success"]:
        return f"I pressed '{key}'."
    else:
        return f"I couldn't press '{key}'. {result.get('error', 'Unknown error')}."


# ── Scroll ───────────────────────────────────────────────────────────────────

def handle_scroll(direction: str, session_id: str) -> str:
    """Scroll up or down at the current mouse position."""
    action_executor.reset_stop()

    result = action_executor.scroll_at(direction)

    _log_action(session_id, "scroll", direction, None, None,
                result["success"], False, result.get("error"))

    if result["success"]:
        return f"I scrolled {direction}."
    else:
        return f"I couldn't scroll {direction}. {result.get('error', 'Unknown error')}."


# ── Drag ─────────────────────────────────────────────────────────────────────

def handle_drag(source: str, target: str, session_id: str) -> str:
    """Drag from one element/coordinate to another."""
    action_executor.reset_stop()

    result = action_executor.drag_between(source, target)

    _log_action(session_id, "drag", f"{source} -> {target}", None, None,
                result["success"], False, result.get("error"))

    if result["success"]:
        return f"I dragged from '{source}' to '{target}'."
    else:
        return f"I couldn't drag. {result.get('error', 'Unknown error')}."


# ── System Search ────────────────────────────────────────────────────────────

def handle_system_search(query: str, session_id: str) -> str:
    """Press Windows key, type query, hit enter."""
    action_executor.reset_stop()
    
    # We can just use the existing keyboard_controller directly for this macro
    from action import keyboard_controller
    import time
    
    try:
        # 1. Open start menu by MANUALLY clicking the taskbar to bypass Windows security
        from vision import ui_automation_engine
        from action import mouse_controller
        
        print("  \033[36m[PANDA] Searching for Taskbar Search/Start button...\033[0m")
        # Try to find "Search" or "Start" on the taskbar
        target_btn = ui_automation_engine.find_element("Search") or ui_automation_engine.find_element("Start")
        
        if target_btn and "bbox" in target_btn:
            bbox = target_btn["bbox"]
            cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
            print(f"  \033[36m[PANDA] Found '{target_btn['name']}' at {cx}, {cy}. Clicking it...\033[0m")
            mouse_controller.click(cx, cy)
        else:
            # Fallback for Windows 11 (bottom center of screen)
            import pyautogui
            sw, sh = pyautogui.size()
            print(f"  \033[33m[PANDA] Taskbar button not found. Guessing Windows 11 bottom-center ({sw//2}, {sh-15}).\033[0m")
            mouse_controller.click(sw // 2, sh - 15)
            
        time.sleep(2.0) # Wait for start menu / search menu to animate open
        
        # 2. Type query
        keyboard_controller.type_text(query, interval=0.05)
        time.sleep(3.0) # Wait for Windows Search to load results
        
        # 3. Hit enter to open the best match
        keyboard_controller.press_key("enter")
        time.sleep(4.0) # Wait for the application to actually launch and gain focus
        
        _log_action(session_id, "system_search", query, None, None, True, False, None)
        return f"I searched the system for '{query}' and opened it."
    except Exception as e:
        _log_action(session_id, "system_search", query, None, None, False, False, str(e))
        return f"I couldn't search the system for '{query}'. Error: {e}"


# ── Stop ─────────────────────────────────────────────────────────────────────

def handle_stop(session_id: str) -> str:
    """Immediately halt any running action."""
    action_executor.stop_all_actions()
    _log_action(session_id, "stop", "user_initiated", None, None, True, False)
    return "I've stopped all actions."


# ── Browser Actions ──────────────────────────────────────────────────────────

def _check_browser_active(action_name: str) -> str | None:
    try:
        from vision.screen_monitor import get_active_window_title
        active_win = get_active_window_title()
        title_lower = active_win.lower()
        is_browser = False
        for browser in ["chrome", "firefox", "edge", "brave", "opera", "safari", "browser", "chromium", "explorer"]:
            if browser in title_lower:
                is_browser = True
                break
        if not is_browser:
            return f"I couldn't execute '{action_name}' because the active window is not a web browser. Active window: '{active_win}'. Please switch to or open a browser first."
    except Exception:
        pass
    return None


def handle_browser_open(url: str, session_id: str) -> str:
    """Open a URL in the Selenium-controlled browser."""
    action_executor.reset_stop()
    try:
        from action.browser_controller import open_url
        result = open_url(url)

        _log_action(session_id, "browser_open", url, None, None,
                    result["success"], False, result.get("error"))

        if result["success"]:
            return f"I opened '{result.get('title', url)}' in the browser."
        else:
            return f"I couldn't open '{url}'. {result.get('error', 'Unknown error')}."
    except Exception as e:
        _log_action(session_id, "browser_open", url, None, None, False, False, str(e))
        return f"Browser error: {e}"


def handle_browser_search(query: str, session_id: str, engine: str = "google") -> str:
    """Search the web using Selenium."""
    action_executor.reset_stop()
    try:
        from action.browser_controller import search
        result = search(query, engine=engine)

        _log_action(session_id, "browser_search", f"{engine}: {query}", None, None,
                    result["success"], False, result.get("error"))

        if result["success"]:
            return f"I searched {engine.title()} for '{query}'."
        else:
            return f"I couldn't search. {result.get('error', 'Unknown error')}."
    except Exception as e:
        _log_action(session_id, "browser_search", query, None, None, False, False, str(e))
        return f"Browser search error: {e}"


def handle_browser_fill(selector: str, text: str, session_id: str) -> str:
    """Fill a field in the browser using a CSS selector."""
    action_executor.reset_stop()
    browser_err = _check_browser_active("browser_fill")
    if browser_err:
        _log_action(session_id, "browser_fill", f"{selector} -> {text[:20]}", None, None, False, False, browser_err)
        return browser_err
    try:
        from action.browser_controller import fill_form_field
        result = fill_form_field(selector, text)

        _log_action(session_id, "browser_fill", f"{selector} -> {text[:20]}", None, None,
                    result["success"], False, result.get("error"))

        if result["success"]:
            return f"I filled the {result.get('field_type', 'field')}."
        else:
            return f"I couldn't fill the field. {result.get('error', 'Unknown error')}."
    except Exception as e:
        _log_action(session_id, "browser_fill", selector, None, None, False, False, str(e))
        return f"Browser error: {e}"


def handle_browser_click(selector: str, session_id: str) -> str:
    """Click an element in the browser using a CSS selector."""
    action_executor.reset_stop()
    browser_err = _check_browser_active("browser_click")
    if browser_err:
        _log_action(session_id, "browser_click", selector, None, None, False, False, browser_err)
        return browser_err
    try:
        from action.browser_controller import click_element_by_selector
        result = click_element_by_selector(selector)

        _log_action(session_id, "browser_click", selector, None, None,
                    result["success"], False, result.get("error"))

        if result["success"]:
            return f"I clicked the {result.get('element_tag', 'element')}."
        else:
            return f"I couldn't click the element. {result.get('error', 'Unknown error')}."
    except Exception as e:
        _log_action(session_id, "browser_click", selector, None, None, False, False, str(e))
        return f"Browser error: {e}"


def handle_browser_scroll(direction: str, session_id: str) -> str:
    """Scroll the browser page."""
    action_executor.reset_stop()
    browser_err = _check_browser_active("browser_scroll")
    if browser_err:
        _log_action(session_id, "browser_scroll", direction, None, None, False, False, browser_err)
        return browser_err
    try:
        from action.browser_controller import scroll_page
        result = scroll_page(direction)

        _log_action(session_id, "browser_scroll", direction, None, None,
                    result["success"], False, result.get("error"))

        if result["success"]:
            return f"I scrolled the browser {direction}."
        else:
            return f"I couldn't scroll. {result.get('error', 'Unknown error')}."
    except Exception as e:
        _log_action(session_id, "browser_scroll", direction, None, None, False, False, str(e))
        return f"Browser error: {e}"


def handle_select_and_copy(target: str, session_id: str) -> str:
    """
    Click on a target element, select all text, copy it, and return the text.
    """
    action_executor.reset_stop()
    before = _capture_before_state(session_id)

    result = action_executor.select_and_copy(target)

    # Verify
    verified = result["success"]
    verify_info = ""
    if result["success"]:
        verify_info = f" Text copied: '{result.get('details', '')}'."
    else:
        verify_info = f" Failed to copy text. Error: {result.get('error', 'Unknown error')}."

    # Log
    coords = result.get("coords")
    _log_action(session_id, "select_and_copy", target,
                coords[0] if coords else None,
                coords[1] if coords else None,
                result["success"], verified,
                result.get("error"))

    if result["success"]:
        return f"I clicked '{target}', selected all, and copied the text.{verify_info}"
    else:
        return f"I couldn't copy text from '{target}'. {result.get('error', 'Unknown error')}."


def handle_undo(target: str, session_id: str) -> str:
    """
    Undo the last click or type action to recover from mistakes.
    """
    action_executor.reset_stop()
    before = _capture_before_state(session_id)
    
    result = action_executor.undo()
    
    # Log
    _log_action(session_id, "undo", "", None, None, result["success"], result["success"], result.get("error"))
    
    return result["details"]


def handle_open_application(app_name: str, web_fallback_url: str, session_id: str) -> str:
    """
    Attempts to open a desktop application if installed locally.
    Otherwise, falls back to opening its web version in the default browser.
    """
    from action import app_detector
    
    action_executor.reset_stop()
    print(f"  [ActionTools] Checking if '{app_name}' is installed locally...")
    
    is_installed = app_detector.is_app_installed(app_name)
    
    if is_installed:
        print(f"  [ActionTools] App '{app_name}' is installed. Launching via System Search...")
        result = handle_system_search(app_name, session_id)
        _log_action(session_id, "open_application", f"{app_name} (local)", None, None, True, True)
        return f"I launched the desktop application '{app_name}'. {result}"
    else:
        fallback_url = web_fallback_url.strip() if web_fallback_url else ""
        if not fallback_url:
            # Construct a default web address if none provided
            fallback_url = f"https://www.google.com/search?q={app_name.replace(' ', '+')}"
            print(f"  [ActionTools] App '{app_name}' not found. Falling back to Google search: {fallback_url}")
            result = handle_browser_search(app_name, session_id)
            _log_action(session_id, "open_application", f"{app_name} (web search fallback)", None, None, True, False)
            return f"I couldn't find the desktop app '{app_name}' installed locally. I searched for it in the browser. {result}"
        else:
            print(f"  [ActionTools] App '{app_name}' not found. Falling back to web URL: {fallback_url}")
            result = handle_browser_open(fallback_url, session_id)
            _log_action(session_id, "open_application", f"{app_name} (web fallback to {fallback_url})", None, None, True, True)
            return f"I couldn't find the desktop app '{app_name}' installed locally. I opened its web version in the browser instead. {result}"

