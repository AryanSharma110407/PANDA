import sys
import os
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import memory_manager
from vision import screen_monitor
from pynput.keyboard import Controller as KController
from pynput.mouse import Controller as MController, Button

def main():
    print("Initializing memory database...")
    memory_manager.initialize_memory()
    
    session_id = "test_monitor_auto_session"
    
    # Clean up previous test observations
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM screen_observations WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    
    print("\\n--- Starting Background Screen Monitor ---")
    screen_monitor.start_background_monitor(session_id, interval=0.2)
    
    print("Simulating keyboard and mouse actions...")
    keyboard = KController()
    mouse = MController()
    
    time.sleep(1)
    
    # Type some characters
    for char in "hello background monitor":
        keyboard.press(char)
        keyboard.release(char)
        time.sleep(0.05)
        
    time.sleep(1)
    
    # Click mouse
    mouse.position = (200, 200)
    mouse.click(Button.left, 1)
    
    time.sleep(2)
    
    print("\\nStopping Background Monitor...")
    screen_monitor.stop_background_monitor()
    
    # Query database
    print("\\nQuerying saved observations from database...")
    observations = memory_manager.get_recent_observations(session_id, limit=20)
    
    if not observations:
        print("[FAIL] No observations recorded in database.")
        sys.exit(1)
        
    print(f"\\n[SUCCESS] Found {len(observations)} observations recorded:")
    observations.reverse()
    found_typing = False
    found_click = False
    
    for idx, obs in enumerate(observations):
        print(f"  {idx+1}. [{obs['created_at'].split('T')[1][:8]}] Active Window: '{obs['active_window']}'")
        print(f"     Observation: {obs['observation_text']}")
        if "hello background monitor" in obs['observation_text']:
            found_typing = True
        if "clicked" in obs['observation_text'].lower():
            found_click = True
            
    if found_typing and found_click:
        print("\\n[PASS] Both typing and click observations detected in SQLite!")
        sys.exit(0)
    else:
        print(f"\\n[FAIL] Missing target events. Found typing: {found_typing}, Found click: {found_click}")
        sys.exit(1)

if __name__ == "__main__":
    main()
