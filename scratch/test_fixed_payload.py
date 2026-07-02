import os
import json
import ollama
from dotenv import load_dotenv

load_dotenv()

def main():
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")
    
    print(f"Connecting to Ollama at {OLLAMA_URL} with model {MODEL_NAME}...")
    client = ollama.Client(host=OLLAMA_URL, headers={"ngrok-skip-browser-warning": "true"})
    
    payload_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_payload.json")
    if not os.path.exists(payload_path):
        print(f"Error: {payload_path} does not exist.")
        return
        
    with open(payload_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
        
    system_prompt = payload["system_prompt"]
    user_prompt = payload["user_prompt"]
    
    # Append the reminder instruction to the end of the user prompt
    user_prompt += """
Based on the goal, task state, current screen observation, and prior experiences, decide the next action to take.
Remember, you must respond ONLY with a JSON object following the format specified in the system instructions, containing the keys: "think", "plan", "action", and "parameters".
"""
    
    print("Querying LLM with fixed payload...")
    try:
        response = client.chat(
            model=MODEL_NAME,
            format='json',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
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
