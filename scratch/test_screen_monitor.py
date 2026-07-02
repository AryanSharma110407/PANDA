import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import memory_manager
from vision import screen_monitor

def main():
    print("Initializing memory database...")
    memory_manager.initialize_memory()
    
    session_id = "test_monitor_session"
    
    # Clean up previous test observations
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM screen_observations WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    
    print("\n--- Starting Background Screen Monitor ---")
    screen_monitor.start_background_monitor(session_id, interval=1.0)
    
    print("\n[Action Required] Please type a few characters (e.g. 'hello') and click once on the screen in the next 5 seconds...")
    time.sleep(6)
    
    print("\nStopping Background Monitor...")
    screen_monitor.stop_background_monitor()
    
    # Query database
    print("\nQuerying saved observations from database...")
    observations = memory_manager.get_recent_observations(session_id, limit=20)
    
    if not observations:
        print("[FAIL] No observations recorded in database.")
        sys.exit(1)
        
    print(f"\n[SUCCESS] Found {len(observations)} observations recorded:")
    # Print them in chronological order
    observations.reverse()
    for idx, obs in enumerate(observations):
        print(f"  {idx+1}. [{obs['created_at'].split('T')[1][:8]}] Active Window: '{obs['active_window']}'")
        print(f"     Observation: {obs['observation_text']}")
        print()
        
    print("[OK] Test passed successfully!")

if __name__ == "__main__":
    main()
