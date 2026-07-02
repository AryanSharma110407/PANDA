"""
PANDA — Task Prompts (Decomposed Architecture)
================================================
Dynamically generates the system prompt for the Actor LLM.

The Actor is focused on a SINGLE active milestone at a time.
It outputs a single flat JSON action. Python manages the milestone
stack and execution state externally.
"""

from action.action_schema import ACTION_SCHEMAS

def get_actor_system_prompt(active_milestone: str, milestone_index: int, total_milestones: int) -> str:
    """
    Builds the Actor system prompt, constrained to the single active milestone.
    
    Args:
        active_milestone: The current milestone string the Actor must achieve.
        milestone_index: 0-based index of the current milestone in the plan.
        total_milestones: Total number of milestones in the plan.
    """
    
    # Format the valid actions as readable schema documentation
    action_docs = []
    for action_type, info in ACTION_SCHEMAS.items():
        # Skip complete and fail — they are handled separately in the prompt
        if action_type in ("complete", "fail"):
            continue
        doc = f"- '{action_type}': {info.get('description', 'Execute this action')}\n  Required parameters: {info.get('required', [])}"
        action_docs.append(doc)
        
    actions_text = "\n".join(action_docs)

    # Fetch lessons and preferences dynamically
    lessons_and_prefs = []
    try:
        import memory_manager
        recent_lessons = memory_manager.load_lessons(limit=5)
        if recent_lessons:
            filtered_lessons = []
            for lesson in recent_lessons:
                txt = lesson.get("lesson_text", "").strip()
                # Skip garbage: raw JSON blobs from test mocks are not real lessons
                if txt and not txt.startswith("{") and not txt.startswith("["):
                    filtered_lessons.append(txt)
            if filtered_lessons:
                lessons_and_prefs.append("Lessons Learned from Past Attempts:")
                for txt in filtered_lessons:
                    lessons_and_prefs.append(f" - {txt}")
        
        active_prefs = memory_manager.load_preferences()
        valid_prefs = []
        for p in active_prefs:
            if p.get("consolidated_to"):
                continue
            txt = p.get("preference_text", "").strip()
            # Skip garbage: raw JSON blobs from test mocks are not real preferences
            if txt and not txt.startswith("{") and not txt.startswith("["):
                valid_prefs.append(txt)
        # Cap at 10 most recent to prevent context bloat for the 8B model
        valid_prefs = valid_prefs[:10]
        if valid_prefs:
            lessons_and_prefs.append("Active User Preferences:")
            for pref in valid_prefs:
                lessons_and_prefs.append(f" - {pref}")
    except Exception:
        pass

    lessons_prefs_block = ""
    if lessons_and_prefs:
        lessons_prefs_block = "==================================================\nLESSONS LEARNED & PREFERENCES\n==================================================\n" + "\n".join(lessons_and_prefs) + "\n==================================================\n\n"

    return f"""{lessons_prefs_block}You are PANDA's Actor — an autonomous agent controlling a desktop computer.
You are working on milestone {milestone_index + 1} of {total_milestones}.

YOUR CURRENT MILESTONE:
>>> {active_milestone} <<<

Your ONLY job is to execute the NEXT SINGLE ACTION that moves you closer to completing this milestone.
Do NOT think about future milestones. Focus entirely on the current one.

CRITICAL RULES:
1. **JSON ONLY**: Output ONLY a single valid JSON object. No conversational text or markdown code blocks.
2. **SINGLE FLAT ACTION**: Output exactly ONE action with flat parameters. No nested dicts. No action lists.
3. **VALID ACTIONS**: Choose actions strictly from the AVAILABLE ACTIONS list below.
4. **TRIAL & ERROR**: If the previous action failed, do NOT repeat it. Try a different approach/action.
5. **LAUNCHING APPS**: ONLY use 'system_search' to launch a completely new software application (e.g., Chrome, Notepad) if it's not currently running. NEVER use 'system_search' to look for buttons, settings, or text inside an already open app.
6. **EXPLORE MENUS & RIGHT CLICK**: If target button is hidden, click dropdowns (e.g. 'File', 'Edit'), settings, or menu icons. If you need to extract data, copy text, or interact with a non-interactive element, try using the 'right_click' action to open a context menu.
7. **MILESTONE COMPLETE**: When THIS specific milestone is fully achieved, use the 'milestone_complete' action.
8. **ACTIVE WINDOWS**: If the target window is active, you do NOT need to click it to focus. Start typing/acting inside it.
9. **COPYING TEXT**: If you need to read, copy, or extract text from a field, label, or element on the screen, use the 'select_and_copy' action with that target. Do NOT try to use browser actions on desktop applications.

AVAILABLE ACTIONS:
{actions_text}
- 'milestone_complete': This specific milestone is achieved. Required parameters: []
- 'fail': The milestone is blocked and cannot be completed. Required parameters: ['reason']

OUTPUT FORMAT (strict):
{{
    "think": "Brief analysis of screen state & what to do next for this milestone",
    "action": "<action_type>",
    "parameters": {{
        "<param_name>": "<value>"
    }}
}}
"""


# Keep backward compatibility alias
def get_agent_system_prompt() -> str:
    """
    Legacy compatibility wrapper. Returns a generic prompt without
    milestone context. Prefer get_actor_system_prompt() instead.
    """
    return get_actor_system_prompt("Complete the user's goal", 0, 1)
