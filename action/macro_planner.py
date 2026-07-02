"""
PANDA — Macro Planner (Decomposer)
====================================
The Decomposer LLM: runs once per task to generate a flat list of
milestone strings from a user goal.

Replaces the old A*-based planner. The LLM now outputs simple string
milestones (no nested JSON, no state graphs), and Python manages the
milestone queue/stack in task_executor.py.
"""

import os
import json
import ollama

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")

_client = ollama.Client(host=OLLAMA_URL, headers={"ngrok-skip-browser-warning": "true"})


def generate_macro_plan(goal_description: str, prior_conversation: str = "") -> dict:
    """
    Analyzes a task goal to produce a flat list of milestone strings.
    
    Returns:
        dict with keys:
        - "missing_variables": list of missing details (empty if none)
        - "clarification_question": question to ask user (empty if none)
        - "milestones": flat list of string milestones (e.g. ["Open Notepad", "Type text", "Save file"])
    """
    prompt = f"""You are PANDA's Decomposer.
Your job is to analyze the user's task. If any critical specific details are missing (like specific content, search queries, or URLs), ask for them.
Otherwise, output the step-by-step milestones to achieve the goal.

Task Goal: "{goal_description}"
Prior Conversation Context (if any): "{prior_conversation}"

CRITICAL RULES:
1. If the Task Goal already contains the details (e.g., "tell him I'll be late" contains the message "I'll be late", "write sick leave letter" contains the letter type), the detail is NOT missing. Do NOT ask for it.
2. If the Goal contains "User clarified: <answer>", read it. If a detail is in the clarification, it is NOT missing.
3. If the user tells you to search for a detail, it is NOT missing. PANDA will search for it.
4. Only ask for details that are absolutely mandatory and completely absent.
5. If details are missing:
   - "missing_variables" must list them.
   - "clarification_question" must be a clear question to ask.
   - "milestones" must be a generic path with placeholders.
6. If no details are missing:
   - "missing_variables" must be [].
   - "clarification_question" must be empty "".
   - "milestones" must be the exact milestone steps to execute.
7. Each milestone must be a short, self-contained instruction (e.g., "Open Google Chrome", "Navigate to youtube.com", "Search for cat videos").
8. Do NOT nest milestones. Output a FLAT list of strings.

You must reply with ONLY a raw JSON object containing these three keys. No markdown blocks or explanations.
Example format:
{{
  "missing_variables": [],
  "clarification_question": "",
  "milestones": ["Open Google Chrome", "Navigate to email client", "Click compose", "Fill recipient field", "Type email body", "Click send"]
}}
"""

    try:
        response = _client.chat(
            model=MODEL_NAME,
            format="json",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1}
        )
        
        raw = response["message"]["content"].strip()
        print(f"  [Decomposer Debug] Raw response: {raw}")
        data = json.loads(raw)
        
        # Ensure correct structure
        missing = data.get("missing_variables", [])
        if not isinstance(missing, list):
            missing = []
        q = data.get("clarification_question", "")
        
        # Support both "milestones" and legacy "path" key
        milestones = data.get("milestones", data.get("path", []))
        if not isinstance(milestones, list):
            milestones = []
            
        # Ensure all milestones are strings
        milestones = [str(m) for m in milestones if m]
            
        # Clean null values
        if not q:
            q = ""
            
        # If missing variables are present, we return them (no execution milestones yet)
        if missing:
            return {
                "missing_variables": missing,
                "clarification_question": q,
                "milestones": []
            }
            
        return {
            "missing_variables": [],
            "clarification_question": "",
            "milestones": milestones
        }
        
    except Exception as e:
        print(f"  [Decomposer] Error generating plan: {e}")
        return {
            "missing_variables": [],
            "clarification_question": "",
            "milestones": []
        }
