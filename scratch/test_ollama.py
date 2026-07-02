import sys
import os
import json
import ollama
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from action.task_prompts import get_agent_system_prompt
from vision.screen_state import build_screen_state

def main():
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")
    
    print(f"Connecting to Ollama at {OLLAMA_URL} with model {MODEL_NAME}...")
    client = ollama.Client(host=OLLAMA_URL, headers={"ngrok-skip-browser-warning": "true"})
    
    prompt = get_agent_system_prompt()
    
    task_state = {
        "goal": "",
        "plan": {
            "completed_subtasks": [],
            "remaining_subtasks": []
        },
        "history": [],
        "completed_steps": [],
        "current_stage": "Initializing"
    }
    
    from vector_memory import semantic_search_trajectories
    print("Searching past experiences for ''...")
    past_experiences = semantic_search_trajectories("", top_k=2)
    
    experiences_str = ""
    if past_experiences:
        experiences_str = "\nPRIOR EXPERIENCES FOUND:\n"
        for idx, exp in enumerate(past_experiences):
            experiences_str += f"\n--- Experience {idx + 1} (Goal: '{exp['goal']}', Outcome: {exp['status']}) ---\n"
            if exp.get("summary"):
                experiences_str += f"Summary/Lesson: {exp['summary']}\n"
            try:
                steps = json.loads(exp["steps_json"])
                experiences_str += "Steps executed:\n"
                for step in steps:
                    experiences_str += f"  - Action: {step.get('action')}({step.get('parameters')}) -> {step.get('result')}\n"
            except Exception:
                experiences_str += f"  (Unable to parse steps JSON)\n"
    else:
        experiences_str = "\nNO PRIOR EXPERIENCES FOUND.\n"

    print("Capturing screen state...")
    try:
        screen = build_screen_state("test_session")
    except Exception as e:
        screen = {"error": str(e), "summary": "Failed to capture screen"}
        
    state_context = f"""
TASK STATE:
{json.dumps(task_state, indent=2)}

SCREEN OBSERVATION:
{json.dumps(screen, indent=2)}

{experiences_str}
"""

    print("Querying LLM...")
    try:
        response = client.chat(
            model=MODEL_NAME,
            format='json',
            messages=[
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': state_context}
            ],
            options={"temperature": 0.1}
        )
        raw = response['message']['content'].strip()
        print("\n--- RAW LLM RESPONSE ---")
        print(raw)
        print("------------------------")
    except Exception as e:
        print(f"Error querying Ollama: {e}")

if __name__ == "__main__":
    main()
