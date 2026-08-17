"""
PANDA Vision — Background Screen and Input Monitor
===================================================
Runs background listeners to track user activity:
1. Window title changes (polling every 1.0s)
2. Mouse clicks (coordinates)
3. Keyboard typing (buffers text in memory and flushes on boundaries)
4. Periodic/event-driven screen capture (OCR + UI Automation + OpenCV)

All entries are saved to the `screen_observations` SQLite table.
"""

import threading
import time
import json
# pyrefly: ignore [missing-import]
import pygetwindow as gw
from pynput import mouse, keyboard
import memory_manager
from vision.screen_state import build_screen_state

# STDP Habit Tracker — experimental spiking neural network for learning habits
try:
    from action import stdp_habit_tracker
    _stdp_available = True
except ImportError:
    _stdp_available = False

# Global State
_stop_event = threading.Event()
_monitor_thread = None
_mouse_listener = None
_keyboard_listener = None

_session_id = "auto_task"
_last_active_window = None
_last_frame_hash = None
_last_capture_time = 0

_key_buffer = []
_buffer_lock = threading.Lock()

_pending_actions = []
_pending_lock = threading.Lock()


def get_active_window_title() -> str:
    """Safely retrieves the current active window title."""
    try:
        from vision import ui_automation_engine
        if ui_automation_engine.is_available():
            focused = ui_automation_engine.get_focused_window()
            if focused and focused.get("title"):
                return focused["title"].strip()
    except Exception:
        pass

    try:
        win = gw.getActiveWindow()
        if win and win.title:
            return win.title.strip()
    except Exception:
        pass

    return "Unknown"


def _flush_buffer(trigger_reason: str):
    """Flushes buffered keystrokes to the pending actions list."""
    global _key_buffer
    with _buffer_lock:
        if not _key_buffer:
            return
        text = "".join(_key_buffer).strip()
        _key_buffer = []

    if text:
        obs_text = f"User typed: '{text}' ({trigger_reason})"
        with _pending_lock:
            _pending_actions.append(obs_text)

        # Feed typed text to STDP habit tracker
        if _stdp_available:
            try:
                stdp_habit_tracker.register_event(f"type:{text.lower().strip()}")
            except Exception:
                pass


def on_click(x, y, button, pressed):
    """Callback for mouse click events."""
    if pressed:
        try:
            # Flush keystrokes before registering click
            _flush_buffer("Mouse click")
            obs_text = f"User clicked at ({x}, {y})"
            with _pending_lock:
                _pending_actions.append(obs_text)

            # Feed click event to STDP habit tracker
            if _stdp_available:
                try:
                    stdp_habit_tracker.register_event(f"click:{x},{y}")
                except Exception:
                    pass
        except Exception:
            pass


def on_press(key):
    """Callback for keyboard keypress events."""
    global _key_buffer
    try:
        if _stop_event.is_set():
            return False  # Stops listener

        with _buffer_lock:
            if hasattr(key, 'char') and key.char is not None:
                _key_buffer.append(key.char)
            elif key == keyboard.Key.space:
                _key_buffer.append(' ')
            elif key == keyboard.Key.enter:
                _flush_buffer("Enter pressed")
            elif key == keyboard.Key.tab:
                _flush_buffer("Tab pressed")
            elif key == keyboard.Key.backspace:
                if _key_buffer:
                    _key_buffer.pop()
    except Exception:
        pass


def _monitor_loop(session_id: str, interval: float):
    """Main loop checking for active window switches and heartbeats with screen captures."""
    global _last_active_window, _last_capture_time, _session_id, _pending_actions, _last_frame_hash
    _session_id = session_id
    _last_capture_time = time.time()

    # 1. Perform an initial screen capture immediately on startup!
    try:
        active_win = get_active_window_title()
        _last_active_window = active_win

        state = build_screen_state(session_id)
        summary = state.get("summary", "No details")
        ocr_json = json.dumps(state.get("visible_text", []))

        obs_text = f"Monitor started. Screen Summary: {summary}"
        memory_manager.add_screen_observation(
            session_id=session_id,
            observation_text=obs_text,
            raw_ocr_text=ocr_json,
            active_window=active_win
        )
        print("[PANDA] Initial screen capture complete.")
    except Exception as e:
        print(f"[PANDA] [WARN] Initial startup screen capture failed: {e}")

    while not _stop_event.is_set():
        try:
            active_win = get_active_window_title()
            curr_time = time.time()

            # Check window switch
            window_switched = False
            if active_win != _last_active_window:
                _flush_buffer("Window switched")
                _last_active_window = active_win
                window_switched = True
                with _pending_lock:
                    _pending_actions.append(f"Active window switched to '{active_win}'.")

                # Feed window switch to STDP habit tracker
                if _stdp_available:
                    try:
                        # Normalize window title to a category
                        win_label = active_win.split(" - ")[-1].strip() if " - " in active_win else active_win
                        stdp_habit_tracker.register_event(f"window:{win_label.lower()}")
                    except Exception:
                        pass

            # Determine if we should perform a screen capture
            has_pending = False
            with _pending_lock:
                has_pending = len(_pending_actions) > 0

            time_elapsed = curr_time - _last_capture_time

            # We capture if:
            # - A window switch occurred
            # - There are pending clicks/typing to record
            # - 0.5 seconds have passed since the last capture (periodic heartbeat)
            if window_switched or has_pending or time_elapsed >= 0.5:
                # Extract all pending action texts
                actions_to_log = []
                with _pending_lock:
                    if _pending_actions:
                        actions_to_log = list(_pending_actions)
                        _pending_actions.clear()

                # Perform screen capture
                from vision.screenshot_manager import capture_screen
                img = capture_screen()
                
                # Check if screen actually changed
                curr_hash = img.resize((16, 16)).convert("L").tobytes()
                
                if _last_frame_hash == curr_hash and _last_active_window == active_win and not has_pending:
                    _last_capture_time = curr_time
                    continue
                    
                _last_frame_hash = curr_hash
                _last_active_window = active_win

                state = build_screen_state(session_id, pre_captured_image=img)
                summary = state.get("summary", "No details")
                ocr_json = json.dumps(state.get("visible_text", []))

                # Construct combined observation text
                if actions_to_log:
                    actions_summary = "; ".join(actions_to_log)
                    obs_text = f"{actions_summary} Screen Summary: {summary}"
                else:
                    obs_text = f"Periodic monitor update. Screen Summary: {summary}"

                memory_manager.add_screen_observation(
                    session_id=session_id,
                    observation_text=obs_text,
                    raw_ocr_text=ocr_json,
                    active_window=active_win
                )
                _last_capture_time = curr_time

        except Exception as e:
            print(f"[ScreenMonitor Error] Exception in background loop: {e}")

        # Check more frequently than interval to catch window switches/actions quickly
        time.sleep(min(0.5, interval))


def start_background_monitor(session_id: str, interval: float = 0.5):
    """Starts window polling and pynput listeners in background threads."""
    global _stop_event, _monitor_thread, _mouse_listener, _keyboard_listener

    # Reset stop event
    _stop_event.clear()

    print(f"[PANDA] Starting background activity monitor (Session: {session_id})...")

    # 1. Start Window Polling Thread
    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        args=(session_id, interval),
        daemon=True
    )
    _monitor_thread.start()

    # 2. Start pynput listeners
    try:
        _mouse_listener = mouse.Listener(on_click=on_click)
        _mouse_listener.daemon = True
        _mouse_listener.start()

        _keyboard_listener = keyboard.Listener(on_press=on_press)
        _keyboard_listener.daemon = True
        _keyboard_listener.start()
    except Exception as err:
        print(f"[PANDA] [WARN] Failed to start input event listeners: {err}")


def stop_background_monitor():
    """Stops all threads and listeners gracefully."""
    global _stop_event, _mouse_listener, _keyboard_listener

    print("[PANDA] Stopping background activity monitor...")

    # Flush remaining keystrokes
    _flush_buffer("Shutdown")

    # Save STDP habit weights before shutdown
    if _stdp_available:
        try:
            stdp_habit_tracker.save_weights()
            print("[PANDA] STDP habit weights saved.")
        except Exception as e:
            print(f"[PANDA] [WARN] Failed to save STDP weights: {e}")

    # Signal threads to stop
    _stop_event.set()

    # Stop pynput listeners
    if _mouse_listener:
        try:
            _mouse_listener.stop()
        except Exception:
            pass
    if _keyboard_listener:
        try:
            _keyboard_listener.stop()
        except Exception:
            pass
