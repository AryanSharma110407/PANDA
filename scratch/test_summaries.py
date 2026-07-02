import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set UTF-8 encoding for standard output on Windows
sys.stdout.reconfigure(encoding='utf-8')

print("--- TESTING PROFILE INJECTION & CONVERSATIONAL SUMMARIES ---")

try:
    import alya
    import smart_brain
    import memory_manager
    
    print("\n1. Testing handle_goal_show():")
    goals_res = alya.handle_goal_show()
    print("RESULT:")
    print(goals_res)
    
    print("\n2. Testing handle_preference_show():")
    prefs_res = alya.handle_preference_show()
    print("RESULT:")
    print(prefs_res)
    
    print("\n3. Testing smart_brain.panda_brain() system prompt compilation:")
    # We will print the compiled system message from panda_brain() (before the Ollama call)
    # We'll run a quick test turn
    try:
        # We temporarily mock client.chat to capture the system message instead of calling Ollama
        orig_chat = smart_brain._ollama_client.chat
        captured_messages = []
        
        def mock_chat(*args, **kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            # Return a mock chunk generator
            class MockResponse:
                def __iter__(self):
                    yield {"message": {"content": "Mock conversational reply."}}
            return MockResponse()
            
        smart_brain._ollama_client.chat = mock_chat
        
        # Call panda_brain
        gen = smart_brain.panda_brain("hello there, what's my profile look like?", context_from_rag="Mock RAG Context")
        reply = "".join(list(gen))
        
        print("Captured system message:")
        system_msg = next((m["content"] for m in captured_messages if m["role"] == "system"), None)
        print(system_msg)
        
        # Restore chat
        smart_brain._ollama_client.chat = orig_chat
    except Exception as mock_err:
        print(f"Error testing panda_brain prompt: {mock_err}")

    print("\n4. Testing offline fallback for handle_goal_show():")
    # Temporarily force invalid OLLAMA_URL
    orig_env = os.environ.get("OLLAMA_URL")
    os.environ["OLLAMA_URL"] = "http://localhost:9999" # invalid URL
    goals_offline_res = alya.handle_goal_show()
    print("OFFLINE RESULT:")
    print(goals_offline_res)
    
    print("\n5. Testing offline fallback for handle_preference_show():")
    prefs_offline_res = alya.handle_preference_show()
    print("OFFLINE RESULT:")
    print(prefs_offline_res)
    
    # Restore env
    if orig_env:
        os.environ["OLLAMA_URL"] = orig_env
    else:
        del os.environ["OLLAMA_URL"]

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
