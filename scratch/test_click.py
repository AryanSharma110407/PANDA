import sys
import os

# Ensure the root directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from action import action_executor
from action import mouse_controller

def test_clicks():
    print("Testing raw mouse_controller.click(10, 10)...")
    try:
        mouse_controller.click(10, 10)
        print("[SUCCESS] mouse_controller.click(10, 10) executed successfully without errors.")
    except Exception as e:
        print(f"[FAILED] mouse_controller.click failed: {e}")

    print("\nTesting action_executor.smart_click with a bounding box string...")
    # This simulates what the LLM passes in
    target_str = "button, bbox: [100, 200, 300, 400]"
    result = action_executor.smart_click(target_str)
    
    if result["success"]:
        print(f"[SUCCESS] smart_click SUCCESS: {result['details']}")
    else:
        print(f"[FAILED] smart_click FAILED: {result['error']}")

if __name__ == "__main__":
    test_clicks()
