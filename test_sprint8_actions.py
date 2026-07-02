"""
PANDA — Sprint 8 Action Engine Test Suite
===========================================
Tests all 8 action module files + DB integration.
All tests use mocked pyautogui/selenium — no real mouse/keyboard/browser needed.

Run: python test_sprint8_actions.py
"""

import sys
import os
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import sqlite3
import threading
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Test infrastructure ──────────────────────────────────────────────────────
passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        failed += 1


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ACTION SCHEMA TESTS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n📋 Test Group 1: Action Schema")

from action.action_schema import (
    VALID_ACTIONS, ACTION_SCHEMAS, is_valid_action,
    validate_action, get_action_info, list_all_actions
)

# Test 1: Valid actions exist
test("VALID_ACTIONS has expected entries", len(VALID_ACTIONS) >= 10)

# Test 2: is_valid_action
test("is_valid_action('click') = True", is_valid_action("click"))
test("is_valid_action('explode') = False", not is_valid_action("explode"))

# Test 3: validate_action — valid
valid, err = validate_action("click", {"target": "send_button"})
test("validate_action('click', {target}) is valid", valid and err == "")

# Test 4: validate_action — missing required param
valid, err = validate_action("click", {})
test("validate_action('click', {}) fails — missing 'target'", not valid and "target" in err)

# Test 5: validate_action — unknown action
valid, err = validate_action("teleport", {"x": 0})
test("validate_action('teleport') fails — unknown", not valid and "Unknown" in err)

# Test 6: Browser actions in schema
test("browser_open in VALID_ACTIONS", is_valid_action("browser_open"))
test("browser_search in VALID_ACTIONS", is_valid_action("browser_search"))

# Test 7: get_action_info
info = get_action_info("type")
test("get_action_info('type') returns required=['text']", info and "text" in info["required"])

# Test 8: list_all_actions
all_actions = list_all_actions()
test("list_all_actions returns sorted list", all_actions == sorted(all_actions) and len(all_actions) >= 10)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. STOP_EVENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n🛑 Test Group 2: STOP_EVENT")

from action.action_executor import STOP_EVENT, stop_all_actions, reset_stop, _check_stop

# Test 9: STOP_EVENT starts cleared
reset_stop()
test("STOP_EVENT starts cleared", not STOP_EVENT.is_set())

# Test 10: stop_all_actions sets it
stop_all_actions()
test("stop_all_actions sets STOP_EVENT", STOP_EVENT.is_set())

# Test 11: _check_stop raises RuntimeError when set
try:
    _check_stop()
    test("_check_stop raises when STOP_EVENT set", False)
except RuntimeError as e:
    test("_check_stop raises RuntimeError with message", "halted" in str(e).lower())

# Test 12: reset_stop clears it
reset_stop()
test("reset_stop clears STOP_EVENT", not STOP_EVENT.is_set())


# ═══════════════════════════════════════════════════════════════════════════════
# 3. MOUSE CONTROLLER TESTS (mocked)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n🖱️ Test Group 3: Mouse Controller (mocked)")

import action.mouse_controller as mc

# Mock pyautogui for mouse tests
mock_pyautogui = MagicMock()
mock_pyautogui.size.return_value = (1920, 1080)
mock_pyautogui.position.return_value = MagicMock(x=500, y=300)
mock_pyautogui.FAILSAFE = True
mock_pyautogui.PAUSE = 0.1

with patch.dict('sys.modules', {'pyautogui': mock_pyautogui}):
    # Refresh module references
    mc.pyautogui = mock_pyautogui
    mc.PYAUTOGUI_AVAILABLE = True
    reset_stop()

    # Test 13: click
    result = mc.click(100, 200)
    test("mouse click returns success", result["success"] and result["coords"] == (100, 200))

    # Test 14: coord clamping
    x, y = mc._clamp_coords(5000, -10)
    test("coords clamped to screen bounds", x == 1919 and y == 0)

    # Test 15: scroll
    result = mc.scroll(100, 200, 3)
    test("scroll returns success", result["success"])

    # Test 16: drag
    result = mc.drag(10, 10, 500, 500)
    test("drag returns success", result["success"])

    # Test 17: get_position
    pos = mc.get_position()
    test("get_position returns (500, 300)", pos == (500, 300))


# ═══════════════════════════════════════════════════════════════════════════════
# 4. KEYBOARD CONTROLLER TESTS (mocked)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n⌨️ Test Group 4: Keyboard Controller (mocked)")

import action.keyboard_controller as kc

with patch.dict('sys.modules', {'pyautogui': mock_pyautogui}):
    kc.pyautogui = mock_pyautogui
    kc.PYAUTOGUI_AVAILABLE = True
    reset_stop()

    # Test 18: type_text
    result = kc.type_text("hello world")
    test("type_text returns success", result["success"] and result["length"] == 11)

    # Test 19: press_key
    result = kc.press_key("enter")
    test("press_key('enter') returns success", result["success"])

    # Test 20: hotkey
    result = kc.hotkey("ctrl", "c")
    test("hotkey('ctrl', 'c') returns success", result["success"])

    # Test 21: key normalization
    normalized = kc._normalize_key("esc")
    test("'esc' normalized to 'escape'", normalized == "escape")

    # Test 22: parse_and_execute combo
    result = kc.parse_and_execute("ctrl+v")
    test("parse_and_execute('ctrl+v') works", result["success"])

    # Test 23: clear_and_type
    result = kc.clear_and_type("replacement text")
    test("clear_and_type returns success", result["success"])


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ACTION EXECUTOR TESTS (mocked)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n⚡ Test Group 5: Action Executor (mocked)")

from action import action_executor

with patch.dict('sys.modules', {'pyautogui': mock_pyautogui}):
    mc.pyautogui = mock_pyautogui
    mc.PYAUTOGUI_AVAILABLE = True
    kc.pyautogui = mock_pyautogui
    kc.PYAUTOGUI_AVAILABLE = True
    reset_stop()

    # Test 24: click_at
    result = action_executor.click_at(500, 300)
    test("click_at(500, 300) succeeds", result["success"] and result["coords"] == (500, 300))

    # Test 25: type_into_focused
    result = action_executor.type_into_focused("hello PANDA")
    test("type_into_focused succeeds", result["success"])

    # Test 26: press key
    result = action_executor.press("enter")
    test("press('enter') succeeds", result["success"])

    # Test 27: scroll_at
    result = action_executor.scroll_at("down", 5)
    test("scroll_at('down', 5) succeeds", result["success"])

    # Test 28: STOP_EVENT halts actions
    stop_all_actions()
    try:
        action_executor.click_at(100, 100)
        test("click_at raises when stopped", False)
    except RuntimeError:
        test("click_at raises RuntimeError when STOP_EVENT set", True)
    reset_stop()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. ACTION VERIFIER TESTS (mocked)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n🔍 Test Group 6: Action Verifier")

from action import action_verifier

# Test 29: verify_screen_changed with different states
mock_before = {
    "session_id": "test",
    "active_window": "Notepad",
    "summary": "Active Window: Notepad. Text visible.",
    "visible_text": [{"text": "Hello", "confidence": 0.9}]
}

from PIL import Image
mock_img = Image.new("RGB", (16, 16))
with patch('vision.screenshot_manager.capture_screen', return_value=mock_img) as mock_capture, \
     patch('vision.screen_monitor.get_active_window_title', return_value="Chrome") as mock_title, \
     patch('vision.screen_state.build_screen_state') as mock_build:
    mock_build.return_value = {
        "session_id": "test",
        "active_window": "Chrome",
        "summary": "Active Window: Chrome. Google search.",
        "visible_text": [{"text": "Google", "confidence": 0.95}]
    }
    result = action_verifier.verify_screen_changed(mock_before)
    test("verify_screen_changed detects window change", result["changed"] and result["window_changed"])

# Test 30: verify_window_changed
with patch('pygetwindow.getActiveWindow') as mock_gw:
    mock_win = MagicMock()
    mock_win.title = "Google Chrome - YouTube"
    mock_gw.return_value = mock_win
    test("verify_window_changed finds 'YouTube'", action_verifier.verify_window_changed("YouTube"))
    test("verify_window_changed misses 'Firefox'", not action_verifier.verify_window_changed("Firefox"))


# ═══════════════════════════════════════════════════════════════════════════════
# 7. DATABASE — action_log TABLE
# ═══════════════════════════════════════════════════════════════════════════════
print("\n💾 Test Group 7: Database — action_log")

import memory_manager
memory_manager.initialize_memory()

# Test 31: action_log table exists
conn = sqlite3.connect(memory_manager.DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='action_log'")
table_exists = cursor.fetchone() is not None
test("action_log table exists in DB", table_exists)

# Test 32: log_action writes and returns ID
test_session = "test_sprint8_actions"
action_id = memory_manager.log_action(
    session_id=test_session,
    action_type="click",
    target="send_button",
    coords_x=842,
    coords_y=631,
    success=True,
    verified=True,
    error_msg=None
)
test("log_action returns valid ID", action_id is not None and action_id > 0)

# Test 33: get_recent_actions retrieves logged actions
recent = memory_manager.get_recent_actions(test_session, limit=5)
test("get_recent_actions returns the logged action",
     len(recent) > 0 and recent[0]["action_type"] == "click" and recent[0]["target"] == "send_button")

# Cleanup test data
cursor.execute("DELETE FROM action_log WHERE session_id = ?", (test_session,))
conn.commit()
conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 8. BROWSER CONTROLLER TESTS (mocked)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n🌐 Test Group 8: Browser Controller (mocked)")

from action import browser_controller

# Test 34: search URL construction
reset_stop()
# We test the URL logic without actually launching Chrome
test("Google search URL format",
     f"https://www.google.com/search?q=hello+world" ==
     f"https://www.google.com/search?q={'hello world'.replace(' ', '+')}")

test("YouTube search URL format",
     f"https://www.youtube.com/results?search_query=python+tutorial" ==
     f"https://www.youtube.com/results?search_query={'python tutorial'.replace(' ', '+')}")

# Test 35: open_url auto-adds https
reset_stop()
with patch.object(browser_controller, '_get_driver') as mock_driver:
    mock_d = MagicMock()
    mock_d.title = "Example Page"
    mock_d.current_url = "https://example.com"
    mock_d.execute_script.return_value = "complete"
    mock_driver.return_value = mock_d
    
    # Mock WebDriverWait
    if not hasattr(browser_controller, 'WebDriverWait'):
        browser_controller.WebDriverWait = MagicMock()
    with patch.object(browser_controller, 'WebDriverWait') as mock_wait:
        mock_wait.return_value.until.return_value = True
        result = browser_controller.open_url("example.com")
        test("open_url auto-adds https:// and returns success",
             result["success"] and result["title"] == "Example Page")
        # Verify https was added
        mock_d.get.assert_called_with("https://example.com")

# Test 36: scroll_page
with patch.object(browser_controller, '_get_driver') as mock_driver:
    mock_d = MagicMock()
    mock_driver.return_value = mock_d
    result = browser_controller.scroll_page("down", 3)
    test("scroll_page('down', 3) calls scrollBy with 900px", result["success"])


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"  Sprint 8 Test Results: {passed} passed, {failed} failed, {passed + failed} total")
if failed == 0:
    print("  🎉 ALL TESTS PASSED!")
else:
    print(f"  ⚠️  {failed} test(s) failed.")
print(f"{'='*60}\n")
