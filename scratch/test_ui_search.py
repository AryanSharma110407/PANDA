import sys
import os

# Ensure the root directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vision import ui_automation_engine
from action import action_executor

def test_find():
    target = "Notepad"
    print(f"Searching UI Automation Tree for '{target}'...")
    element = ui_automation_engine.find_element(target)
    if element:
        print(f"✅ Found element: {element}")
    else:
        print(f"❌ Could not find element '{target}'")

if __name__ == "__main__":
    test_find()
