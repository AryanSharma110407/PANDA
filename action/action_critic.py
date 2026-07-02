"""
PANDA — Action Critic (Plan 2)
===============================
A lightweight validation module that acts as an Overseer / Critic.
It critiques proposed actions before they are executed to prevent hallucinations
(such as using system_search to look for button elements inside open windows).
"""

import os
import json
import ollama
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")

_client = ollama.Client(host=OLLAMA_URL, headers={"ngrok-skip-browser-warning": "true"})

def critique_action(goal: str, screen_state_summary: str, proposed_action: dict) -> dict:
    """
    Critiques a proposed action against the target goal and the current screen state summary.
    Returns a dict with key 'approved' (bool) and 'feedback' (str).
    """
    system_prompt = """You are PANDA's Overseer Critic. Your job is to inspect proposed actions before they are executed.
Be supportive and lenient. Approve the action if it is reasonable, even if it is not the most optimal choice. Only reject the action if it is a clear mistake, dangerous, or a major hallucination.

CRITICAL RED FLAGS to reject:
1. System Search Over-reliance: PANDA must ONLY use 'system_search' to launch a completely new application (e.g. Notepad, Chrome, AnyDesk). PANDA must NEVER use 'system_search' to look for buttons, settings, text, or links inside an already open/visible application.
2. Repetitive Actions: Critique if PANDA is repeating an action that recently failed or is stuck in an infinite loop without changing parameters or target.
3. Completely Irrelevant/Nonsensical Actions: Critique if the action has absolutely nothing to do with the goal (e.g., trying to write text on an empty space when a text box is not selected/visible).

IMPORTANT: If the proposed action is reasonable, logical, or you are not 100% sure it is incorrect, you MUST approve it. When in doubt, approve.

Analyze the proposed action against the goal and the current screen state.
You must output a JSON object with EXACTLY the following keys:
{
  "approved": true or false,
  "feedback": "A detailed explanation of why the action is approved or rejected. If rejected, provide clear redirection instructions on what alternative actions should be taken instead."
}
"""

    user_prompt = f"""GOAL: {goal}
CURRENT SCREEN STATE SUMMARY: {screen_state_summary}
PROPOSED ACTION: {json.dumps(proposed_action, indent=2)}

Please evaluate and output JSON:"""

    try:
        response = _client.chat(
            model=MODEL_NAME,
            format='json',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            options={"temperature": 0.0}  # Deterministic check
        )
        content = response['message']['content'].strip()
        
        # Clean possible markdown
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        result = json.loads(content)
        if not isinstance(result, dict) or "approved" not in result or "feedback" not in result:
            return {"approved": True, "feedback": "Fallback: Invalid overseer JSON response, permitting action."}
            
        return {
            "approved": bool(result["approved"]),
            "feedback": str(result["feedback"])
        }
    except Exception as e:
        # Fallback to approve on LLM connection failure
        return {"approved": True, "feedback": f"Critic warning (LLM exception): {e}"}
