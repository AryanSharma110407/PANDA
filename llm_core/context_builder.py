# Context Builder & Prompt Assembly Engine
# Part of llm_core

import os
import re

# Style triggers
_CONCISE_TRIGGERS = {"brief", "short", "summarize", "summary", "quickly", "in short", "tldr"}
_DETAILED_TRIGGERS = {"detail", "detailed", "explain fully", "deep", "with examples",
                      "elaborate", "in depth", "thoroughly", "step by step"}

_STYLE_INSTRUCTIONS = {
    "concise":  "Give a short, clear answer in 2–4 lines. No extra explanation.",
    "normal":   "Give a clear explanation with key points. Keep it moderately detailed.",
    "detailed": "Give a detailed explanation with examples, breakdown, and structured points.",
}

_STYLE_TOKEN_LIMITS = {
    "concise":  256,
    "normal":   512,
    "detailed": 1024,
}

_MATH_TRIGGERS = {
    "calculate", "solve", "equation", "derivative", "integral",
    "simplify", "factor", "proof", "compute", "evaluate",
    "differentiate", "integrate", "matrix", "determinant",
    "what is", "how much", "how many", "convert", "percentage",
}

def _detect_style(user_input: str) -> str:
    text = user_input.lower()
    for trigger in _DETAILED_TRIGGERS:
        if trigger in text:
            return "detailed"
    for trigger in _CONCISE_TRIGGERS:
        if trigger in text:
            return "concise"
    return "normal"

def _detect_temperature(user_input: str) -> float:
    text = user_input.lower()
    if any(trigger in text for trigger in _MATH_TRIGGERS):
        return 0.2
    return 0.7

def build_context(user_input: str, context_from_rag: str = "", conversation_history: list = None, session_id: str = None) -> tuple:
    """
    Constructs the system prompt, styles, temperature, and gathers contextual 
    data (timeline, profile, next steps) from the database to build the message window.
    """
    import memory_manager
    
    if not context_from_rag:
        try:
            low = user_input.lower().strip()
            screen_kws = (
                "screen", "window", "tab", "open", "see", "look", "visible", 
                "current", "currently", "now", "active", "notepad", "shown",
                "browser", "brave", "chrome", "edge", "desktop", "what am i",
                "doing", "watching", "how many", "what is on", "whats on",
                "what's on", "opened", "read the text"
            )
            is_screen_query = any(kw in low for kw in screen_kws)
            
            if not is_screen_query:
                import vector_memory
                matches = vector_memory.semantic_search(user_input, top_k=5)
                if matches:
                    vector_memory.record_retrieved_memories(matches)
                    rag_lines = []
                    for m in matches:
                        time_part = m["timestamp"].split("T")[0] if "T" in m["timestamp"] else m["timestamp"]
                        rag_lines.append(
                            f"[{time_part} (similarity: {m['similarity']:.2f})]: "
                            f"User: '{m['user_message']}' -> Assistant: '{m['assistant_response']}'"
                        )
                    context_from_rag = "\n".join(rag_lines)
                    print(f"  \033[33m🔗 RAG injected {len(matches)} historical memories.\033[0m")
        except Exception as e:
            print(f"  [SmartBrain] RAG injection warning: {e}")

    style = _detect_style(user_input)
    style_instruction = _STYLE_INSTRUCTIONS[style]
    token_limit = _STYLE_TOKEN_LIMITS[style]
    temperature = _detect_temperature(user_input)

    from personality import get_panda_persona
    system_msg = get_panda_persona()

    system_msg += (
        "\n\nCONVERSATION-MODE RULES:\n"
        "1. **NO INTROS**: Never introduce yourself, say your name, or start with conversational fillers like 'Certainly', 'Of course', 'Great question'.\n"
        "2. **NO LISTS**: Do NOT answer in lists or bullet points. Present all descriptions, summaries, and answers in continuous, flowing paragraphs.\n"
        "3. **SCREEN TIMELINE**: Refer to the background monitoring activity timelines to answer questions about what Aryan (the user) recently did, opened, or typed on their screen.\n"
        "4. **SPEAK NATURALLY**: Use contractions (I'm, it's, that's). Talk like a smart friend, not a corporate bot.\n\n"
        f"Style Guideline: {style_instruction}"
    )
    if context_from_rag:
        system_msg += f"\nUse this context: {context_from_rag}"

    try:
        active_goals = memory_manager.load_goals(status='active')
        preferences = memory_manager.load_preferences()
        
        top_goals = [g for g in active_goals if g.get('mention_count', 0) >= 2]
        top_prefs = [p for p in preferences if p.get('mention_count', 0) >= 2]
        
        top_goals.sort(key=lambda x: x.get('mention_count', 0), reverse=True)
        top_prefs.sort(key=lambda x: x.get('mention_count', 0), reverse=True)
        
        top_goals = top_goals[:5]
        top_prefs = top_prefs[:5]
        
        profile_sections = []
        if top_goals:
            goals_str = "\n".join([f"  - {g['goal_text']}" for g in top_goals])
            profile_sections.append(f"Active Goals:\n{goals_str}")
        if top_prefs:
            prefs_str = "\n".join([f"  - {p['preference_text']}" for p in top_prefs])
            profile_sections.append(f"Preferences:\n{prefs_str}")
            
        if profile_sections:
            profile_prompt = "\n\nUSER PROFILE (Aryan's key preferences & active goals, adapt your responses to align with these naturally):\n" + "\n\n".join(profile_sections)
            system_msg += profile_prompt

        try:
            import goal_engine
            top_goal_info = goal_engine.get_highest_priority_goal_with_next_step()
            if top_goal_info:
                goal_engine_prompt = (
                    f"\n\n[PANDA GOAL ENGINE]\n"
                    f"Top active goal: \"{top_goal_info['goal_text']}\" (Priority {top_goal_info['priority']} — v{top_goal_info['plan_version']} plan, {top_goal_info['progress_pct']:.0%} complete)\n"
                    f"Next action: \"{top_goal_info['next_step']}\"\n"
                    f"Instruction: Mention this naturally if relevant (e.g. user mentions work, learning, productivity). Do not force it into every reply."
                )
                system_msg += goal_engine_prompt
        except Exception as goal_engine_err:
            print(f"  [SmartBrain] Goal Engine injection warning (non-fatal): {goal_engine_err}")

        try:
            sess_id = session_id or memory_manager.get_last_session_id()
            if sess_id:
                recent_obs = memory_manager.get_recent_observations(sess_id, limit=8)
                if recent_obs:
                    recent_obs.reverse()
                    timeline_lines = []
                    for obs in recent_obs:
                        created_at = obs.get("created_at", "")
                        time_str = created_at.split("T")[-1][:8] if "T" in created_at else ""
                        time_prefix = f"[{time_str}] " if time_str else ""
                        timeline_lines.append(f"{time_prefix}Active Window: \"{obs['active_window']}\" | Action/Screen: {obs['observation_text']}")
                    
                    timeline_text = "\n".join(timeline_lines)
                    system_msg += (
                        f"\n\n[RECENT BACKGROUND MONITOR ACTIVITY (TIMELINE, OLDEST TO NEWEST)]:\n"
                        f"{timeline_text}\n"
                    )

                recent_acts = memory_manager.get_recent_actions(sess_id, limit=8)
                if recent_acts:
                    recent_acts.reverse()
                    action_lines = []
                    for act in recent_acts:
                        created_at = act.get("created_at", "")
                        time_str = created_at.split("T")[-1][:8] if "T" in created_at else ""
                        time_prefix = f"[{time_str}] " if time_str else ""
                        success_str = "Success" if act.get("success") else "Failed"
                        action_lines.append(f"{time_prefix}Action: {act['action_type']} | Target: {act['target']} | Status: {success_str}")
                    
                    action_text = "\n".join(action_lines)
                    system_msg += (
                        f"\n\n[RECENT PHYSICAL ACTIONS YOU (PANDA) TOOK (TIMELINE, OLDEST TO NEWEST)]:\n"
                        f"{action_text}\n"
                        f"Use this list of actions you recently performed to answer questions about what you just did."
                    )
        except Exception as vision_err:
            print(f"  [SmartBrain] Vision/Action injection warning (non-fatal): {vision_err}")
    except Exception as profile_err:
        print(f"  [SmartBrain] Profile injection warning (non-fatal): {profile_err}")

    if conversation_history:
        system_msg += (
            "\n\nMEMORY GROUNDING — CRITICAL RULE: "
            "The conversation messages passed to you are your COMPLETE memory of this session. "
            "Only refer to topics, facts, or exchanges that actually appear in those messages. "
            "If you are unsure whether something was discussed, say so honestly — for example: "
            "\"I don't think we've talked about that yet — want to get into it now?\" "
            "NEVER fabricate or assume past exchanges that are not in the history."
        )

    messages = [{'role': 'system', 'content': system_msg}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({'role': 'user', 'content': user_input})

    return messages, token_limit, temperature
