import os
import sys
from pathlib import Path

# Set up paths
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

import alya
import smart_brain
import memory_manager

def test_timeline_injection():
    print("--- Testing Timeline Injection ---")
    session_id = "test_verify_session"
    memory_manager.initialize_memory()
    
    # Add a mock observation
    obs_id = memory_manager.add_screen_observation(
        session_id=session_id,
        observation_text="User opened Chrome and searched for 'PyTorch tutorials'",
        raw_ocr_text='[]',
        active_window="Google Chrome"
    )
    print(f"Added mock observation with ID: {obs_id}")
    
    # 1. Test timeline in llm_thinking_engine context
    try:
        from alya import llm_thinking_engine
        # We can intercept or print the prompt by calling it, but since it makes a real Ollama call,
        # let's mock _ollama.chat to see the messages sent.
        original_chat = alya._ollama.chat
        messages_sent = []
        
        def mock_chat(*args, **kwargs):
            messages_sent.extend(kwargs.get("messages", []))
            # Return dummy json response to satisfy the loader
            return {"message": {"content": '{"action": "respond", "params": {}}'}}
            
        alya._ollama.chat = mock_chat
        
        llm_thinking_engine("what was I just looking at?", conversation_history=[], session_id=session_id)
        
        # Restore chat
        alya._ollama.chat = original_chat
        
        # Inspect system prompt
        system_content = next((m["content"] for m in messages_sent if m["role"] == "system"), "")
        print("System prompt timeline search:")
        if "[RECENT BACKGROUND MONITOR ACTIVITY (TIMELINE, OLDEST TO NEWEST)]:" in system_content:
            print("  [PASS] Timeline section exists in system prompt!")
            if "Google Chrome" in system_content and "PyTorch tutorials" in system_content:
                print("  [PASS] Observation details (active window and description) are injected!")
            else:
                print("  [FAIL] Injected observation text not found.")
        else:
            print("  [FAIL] Timeline section missing from system prompt.")
            
    except Exception as e:
        print(f"Error checking timeline injection: {e}")

def test_list_free_rules():
    print("\n--- Testing List-Free Rules in panda_brain Prompt ---")
    # Verify the rule is in system prompt of panda_brain
    try:
        # Generate dummy generator
        gen = smart_brain.panda_brain("hello", conversation_history=[], session_id="test_session")
        # Since it calls Ollama immediately, we want to inspect the prompt before calling it,
        # but let's check smart_brain's client.chat mock to inspect prompt.
        original_chat = smart_brain._ollama_client.chat
        system_prompt_inspected = ""
        
        def mock_chat_sb(*args, **kwargs):
            nonlocal system_prompt_inspected
            system_prompt_inspected = next((m["content"] for m in kwargs.get("messages", []) if m["role"] == "system"), "")
            # Return empty iterator or simple mock chunk
            class MockResponse:
                def __iter__(self):
                    yield {"message": {"content": "Hello"}}
            return MockResponse()
            
        smart_brain._ollama_client.chat = mock_chat_sb
        
        # Consume the generator to trigger the chat call
        list(gen)
        
        # Restore chat
        smart_brain._ollama_client.chat = original_chat
        
        print("System prompt list-free rules search:")
        if "NEVER answer in terms of lists" in system_prompt_inspected or "NEVER use bullet points" in system_prompt_inspected:
            print("  [PASS] List-free rule found in system prompt!")
        else:
            print("  [FAIL] List-free rule missing from system prompt.")
            
    except Exception as e:
        print(f"Error checking list-free rules: {e}")

if __name__ == "__main__":
    test_timeline_injection()
    test_list_free_rules()
