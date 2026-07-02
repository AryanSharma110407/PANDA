import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import smart_brain
import memory_manager

def main():
    print("Loading last session ID...")
    sess_id = memory_manager.get_last_session_id()
    print(f"Session ID: {sess_id}")
    
    # Query observations to see what is in there
    obs = memory_manager.get_recent_observations(sess_id, limit=8)
    print(f"Recent observations count: {len(obs)}")
    for o in obs:
        print(f"  [{o['active_window']}] {o['observation_text']}")
        
    print("\nRunning panda_brain conversational stream...")
    try:
        stream = smart_brain.panda_brain(
            "what did I just type and click?",
            conversation_history=[],
            session_id=sess_id
        )
        print("Yielded chunks:")
        for chunk in stream:
            print(chunk, end="", flush=True)
        print("\nStream finished successfully.")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
