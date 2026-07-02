import sys
import os
import time

# Ensure the root directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from action import mouse_controller
from action import keyboard_controller
import pyautogui

def test_interactive_ui():
    print("==================================================")
    print("Starting Interactive UI Automation Test in 3 seconds...")
    print("IMPORTANT: Do NOT touch your mouse or keyboard.")
    print("You will see smooth, steady cursor movements!")
    print("==================================================")
    time.sleep(3)

    screen_w, screen_h = pyautogui.size()
    cx, cy = screen_w // 2, screen_h // 2

    print("\n[Test 1] Smooth move to center of screen...")
    mouse_controller.move_to(cx, cy, duration=1.0)
    time.sleep(1)

    print("[Test 2] Smooth click (moves to top-left area: 150, 150)...")
    mouse_controller.click(150, 150)
    time.sleep(1)

    print("[Test 3] Smooth right click (moves to 250, 250)...")
    mouse_controller.right_click(250, 250)
    time.sleep(1)
    
    print("         Closing context menu with 'ESC' key...")
    keyboard_controller.press_key("esc")
    time.sleep(1)

    print("[Test 4] Smooth double click (moves to 350, 350)...")
    mouse_controller.double_click(350, 350)
    time.sleep(1)

    print("[Test 5] Human-speed typing...")
    mouse_controller.click(cx, cy) # Click center to focus
    keyboard_controller.type_text("Hello from PANDA! This is typed at a steady speed.", interval=0.05)
    time.sleep(1)

    print("[Test 6] Single key press (Enter)...")
    keyboard_controller.press_key("enter")
    time.sleep(1)
    
    print("\n[SUCCESS] All UI automation functions tested successfully!")

if __name__ == "__main__":
    test_interactive_ui()
