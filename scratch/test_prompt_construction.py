import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import smart_brain
import memory_manager

def main():
    sess_id = memory_manager.get_last_session_id()
    print(f"Active Session ID: {sess_id}")
    
    # 1. Log a test action to verify the database writes successfully
    print("Logging a test action...")
    memory_manager.log_action(
        session_id=sess_id,
        action_type="click",
        target="Notepad File Menu",
        coords_x=50,
        coords_y=80,
        success=True,
        verified=True
    )
    
    # 2. Mock Ollama so it prints the prompt instead of attempting a network connection
    class MockOllama:
        def chat(self, model, messages, stream, options):
            print("\n" + "="*50)
            print(" SYSTEM PROMPT INJECTED FOR CONVERSATION:")
            print("="*50)
            print(messages[0]['content'])
            print("="*50 + "\n")
            return []
            
    smart_brain._ollama_client = MockOllama()
    
    print("\nGenerating conversation context...")
    list(smart_brain.panda_brain("What did I just click?", [], session_id=sess_id))

if __name__ == "__main__":
    main()
