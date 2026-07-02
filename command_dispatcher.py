from datetime import datetime
import os, sys, time, queue, threading
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from console_ui import _stream_typewriter, _stream_and_collect
from voice_orchestrator import voice
from perception_tools import get_continuous_listener

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")
try:
    from perception_tools import listen_to_user as _listen_once
    _PERCEPTION_AVAILABLE = True
except ImportError:
    _PERCEPTION_AVAILABLE = False
    def _listen_once():
        return {"status": "error", "message": "perception_tools not available."}
# ─── Import PANDA's Modules ──────────────────────────────────────────────────

from smart_brain import SmartBrain, panda_brain, _is_question
from memory import PandaMemory, ConversationManager  # merged Mark V module
from personality import (
    get_contextual_greeting,
    check_easter_egg, get_mood_response, get_roadmap
)
from system_ops import (
    open_app, open_website, search_google, search_youtube,
    get_system_info, take_screenshot, open_project_folder,
    open_weather, open_news, list_apps, list_sites, APPS, WEBSITES
)
from task_manager import (
    add_todo, show_todos, complete_todo, remove_todo, clear_completed,
    save_note, show_notes, clear_notes
)
from study_tools import (
    start_timer, set_reminder, show_schedule
)
from tool_registry import run_tool, list_tools
from fusion_layer import (
    fuse,
    get_state       as _fsm_state,
    cancel          as _fsm_cancel,
    get_pending_intent as _fsm_pending_intent,
)
from entity_extractor import extract_entities

# BANNER
# ═══════════════════════════════════════════════════════════════════════════════

BANNER = """
\033[36m
  ██████╗  █████╗ ███╗   ██╗██████╗  █████╗ 
  ██╔══██╗██╔══██╗████╗  ██║██╔══██╗██╔══██╗
  ██████╔╝███████║██╔██╗ ██║██║  ██║███████║
  ██╔═══╝ ██╔══██║██║╚██╗██║██║  ██║██╔══██║
  ██║     ██║  ██║██║ ╚████║██████╔╝██║  ██║
  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝ ╚═╝  ╚═╝
\033[0m
\033[33m  ╔══════════════════════════════════════════════╗
  ║  Proactive Autonomous Neural Directive Agent ║
  ║       ⚡ MARK IV — Real-Time Reactive ⚡       ║
  ║  Piper TTS + faster-whisper + Interrupt Sys  ║
  ╚══════════════════════════════════════════════╝\033[0m
"""


# ═══════════════════════════════════════════════════════════════════════════════
# HELP TEXT
# ═══════════════════════════════════════════════════════════════════════════════

HELP_TEXT = """
\033[36m╔══════════════════════════════════════════════════════════╗
║                  ✨ PANDA COMMANDS                      ║
╚══════════════════════════════════════════════════════════╝\033[0m

  \033[33m💬 BASICS\033[0m
     hello/hi          — Greeting
     time              — Current time
     date              — Current date
     motivate          — Motivational quote
     roadmap           — AI/ML career roadmap
     help              — Show this help
     voice on          — Enable PANDA's voice (Piper TTS)
     voice off         — Disable PANDA's voice

  \033[33m🖥️  SYSTEM\033[0m
     open <app>        — Open Notepad, Calculator, VS Code...
     apps              — List all available apps
     system info       — CPU, RAM, disk dashboard
     screenshot        — Take a screenshot
     folder            — Open project folder

  \033[33m🌐 WEB\033[0m
     open <site>       — Open YouTube, GitHub, Gmail...
     sites             — List all available websites
     search <query>    — Google search
     yt <query>        — YouTube search
     weather           — Weather forecast
     news              — Tech news

  \033[33m📋 TASKS\033[0m
     todo add <task>   — Add a to-do
     todo show         — View all tasks
     todo done <#>     — Complete a task
     todo remove <#>   — Delete a task
     todo clear        — Remove completed tasks

  \033[33m📝 NOTES\033[0m
     note <text>       — Save a quick note
     notes show        — View all notes
     notes clear       — Delete all notes

  \033[33m📚 STUDY\033[0m
     timer <min>       — Study timer
     remind <min> <msg>— Set a reminder
     schedule          — Daily schedule

  \033[33m🎭 FUN — just ask naturally!\033[0m
     "tell me a joke"  — Generated fresh ✨
     "give me a fact"  — Something cool
     "motivate me"     — A quote
     "calc 25 * 4"     — Does the math
     stats             — Your PANDA usage stats

  \033[33m🎤 VOICE\033[0m
     voice on          — Enable Piper TTS output
     voice off         — Disable TTS output
     voice in          — 🎤 MIC ON  (continuous listening)
     voice out         — 🔇 MIC OFF (back to text input)
     voice status      — Show voice/mic state
     voice             — One-shot voice input (single utterance)

  \033[35m💡 Mark IV: Natural language works too!\033[0m
     "what time is it?" → time
     "open youtube for me" → open youtube
     "set a timer for 25 minutes" → timer 25
     "add buy groceries to my todo" → todo add buy groceries

  Type \033[31m'quit'\033[0m or \033[31m'exit'\033[0m to shut down.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# INTENT HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

def handle_intent(intent, entities, user_input, memory):
    """
    Routes an intent to the appropriate handler function.
    Returns the response string, or None to fall through to Venessa.
    """

    # ─── BASIC COMMANDS ───────────────────────────────────────────────
    if intent == "greeting":
        return get_contextual_greeting()

    elif intent == "time":
        now = datetime.now().strftime("%I:%M %p")
        return f"🕐 It's {now}"

    elif intent == "date":
        today = datetime.now().strftime("%A, %B %d, %Y")
        return f"📅 Today is {today}"

    elif intent == "roadmap":
        return get_roadmap()

    elif intent == "help":
        return HELP_TEXT

    # ─── SYSTEM COMMANDS ──────────────────────────────────────────────
    elif intent == "system_info":
        return get_system_info()

    elif intent == "screenshot":
        return take_screenshot()

    elif intent == "folder":
        return open_project_folder()

    elif intent == "apps_list":
        return list_apps()

    elif intent == "sites_list":
        return list_sites()

    # ─── TASK COMMANDS ────────────────────────────────────────────────
    elif intent == "todo_add":
        task = entities.get("value", "").strip()
        if not task:
            text = user_input.lower()
            for prefix in ["todo add ", "add task ", "add todo "]:
                if prefix in text:
                    task = user_input[text.index(prefix) + len(prefix):].strip()
                    break
        if task:
            return add_todo(task)
        return "❌ What task should I add? Try 'todo add study for exam'"

    elif intent == "todo_show":
        return show_todos()

    elif intent == "todo_done":
        number = entities.get("value", "").strip()
        if number:
            result = complete_todo(number)
            if "🎉" in result:
                memory.record_todo_completed()
            return result
        return "❌ Which task? Try 'todo done 1'"

    elif intent == "todo_remove":
        number = entities.get("value", "").strip()
        if number:
            return remove_todo(number)
        return "❌ Which task? Try 'todo remove 1'"

    elif intent == "todo_clear":
        return clear_completed()

    # ─── NOTES ────────────────────────────────────────────────────────
    elif intent == "note_add":
        note = entities.get("value", "").strip()
        if not note:
            text = user_input.lower()
            if text.startswith("note "):
                note = user_input[5:].strip()
        if note:
            return save_note(note)
        return "❌ What should I note down? Try 'note remember to review chapter 5'"

    elif intent == "notes_show":
        return show_notes()

    elif intent == "notes_clear":
        return clear_notes()

    # ─── STUDY TOOLS ──────────────────────────────────────────────────
    elif intent == "timer":
        minutes = entities.get("value", "").strip()
        if not minutes:
            import re
            nums = re.findall(r'\d+', user_input)
            minutes = nums[0] if nums else ""
        if minutes:
            return start_timer(minutes)
        return "❌ How many minutes? Try 'timer 25'"

    elif intent == "reminder":
        minutes = entities.get("value", "").strip()
        message = entities.get("extra", "").strip()
        if minutes and message:
            return set_reminder(minutes, message)
        return "❌ Usage: remind <minutes> <message>. Example: remind 30 take a break"

    elif intent == "schedule":
        return show_schedule()

    # ─── PERSONALITY ──────────────────────────────────────────────────
    elif intent == "stats":
        return memory.get_stats()

    # ─── MOOD ─────────────────────────────────────────────────────────
    elif intent == "mood_bored":
        return get_mood_response("bored")

    elif intent == "mood_tired":
        return get_mood_response("tired")

    elif intent == "mood_stressed":
        return get_mood_response("stressed")

    # ─── VOICE CONTROL ────────────────────────────────────────────────
    elif intent == "voice_on":
        return voice.enable()

    elif intent == "voice_off":
        return voice.disable()

    elif intent == "voice_in":
        # MIC ON — start ContinuousListener from perception_tools
        if _PERCEPTION_AVAILABLE:
            listener = get_continuous_listener()
            return listener.start()
        return "❌ Mic not available. Install faster-whisper and pyaudio."

    elif intent == "voice_out":
        # MIC OFF — stop ContinuousListener
        if _PERCEPTION_AVAILABLE:
            listener = get_continuous_listener()
            return listener.stop()
        return "🔇 Mic is not running."

    elif intent == "voice_status":
        lines = [voice.get_status()]
        if _PERCEPTION_AVAILABLE:
            listener = get_continuous_listener()
            mic_state = "ON (continuous)" if listener.is_running() else "OFF"
            lines.append(f"[Mic]   Status : {mic_state}")
        return "\n".join(lines)

    elif intent == "reflect":
        return handle_reflect()

    elif intent == "show_reflections":
        return handle_reflections_show()

    # ─── QUIT ─────────────────────────────────────────────────────────
    elif intent == "quit":
        user_lower = user_input.strip().lower()
        if user_lower in ("quit", "exit"):
            return "__QUIT__"
        return None

    # ─── UNKNOWN ──────────────────────────────────────────────────────
    else:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACK RESPONSES
# ═══════════════════════════════════════════════════════════════════════════════

import random

FALLBACK_RESPONSES = [
    "🤔 I didn't quite get that. Try 'help' to see what I can do!",
    "✨ Hmm, not sure what you mean. Type 'help' for a list of commands!",
    "❓ I don't understand that yet. Try rephrasing or type 'help'!",
    "🧠 Still learning! I didn't catch that — try 'help' to see my abilities.",
    "💡 Not sure about that one. Type 'help' to see everything I can do!",
]

# Words that abort a pending slot-fill conversation
_CANCEL_WORDS = frozenset({
    "cancel", "never mind", "nevermind", "forget it",
    "forget that", "stop", "abort", "scratch that", "nvm",
})


# ═══════════════════════════════════════════════════════════════════════════════
# VENESSA INTENT FALLBACK BRIDGE
# ═══════════════════════════════════════════════════════════════════════════════

import ollama
_ollama = ollama.Client(
    host=OLLAMA_URL,
    timeout=120.0,
    headers={"ngrok-skip-browser-warning": "true"}
)

KNOWN_INTENTS = [
    "greeting", "time", "date", "roadmap", "help",
    "system_info", "screenshot", "folder", "apps_list", "sites_list", "execute_task",
    "todo_add", "todo_show", "todo_done", "todo_remove", "todo_clear",
    "note_add", "notes_show", "notes_clear",
    "timer", "reminder", "schedule",
    "stats",
    "mood_bored", "mood_tired", "mood_stressed",
    "voice_on", "voice_off", "voice_in", "voice_out", "voice_status",
    "reflect", "show_reflections",
    "quit",
]

def venessa_intent_fallback(user_input, memory):
    """
    Called when PANDA's NLU pipeline returns None (no intent matched).
    Asks Venessa to classify the intent, then runs handle_intent().
    Falls back to conversational reply if intent is "none".
    """
    import json

    system_msg = (
        "You are PANDA's intent-detection engine. "
        "Decide which intent best matches the user's message.\n"
        "Intents: " + ", ".join(KNOWN_INTENTS) + "\n\n"
        "Rules:\n"
        "- Reply with ONLY a JSON object: "
        '{"intent": "<name>", "value": "<extracted value if any>"}\n'
        '- If no intent matches, reply: {"intent": "none"}\n'
        "No markdown, no explanation."
    )

    try:
        response = _ollama.chat(
            model=MODEL_NAME,
            format='json',
            messages=[
                {'role': 'system', 'content': system_msg},
                {'role': 'user',   'content': user_input},
            ]
        )
        raw = response['message']['content'].strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)

    except Exception:
        parsed = {"intent": "none"}

    detected_intent = parsed.get("intent", "none").strip()
    detected_value  = parsed.get("value", "").strip()

    if detected_intent and detected_intent != "none" and detected_intent in KNOWN_INTENTS:
        entities = {"value": detected_value}
        print(f"  \033[33m🧠 Venessa mapped → '{detected_intent}'\033[0m")
        result = handle_intent(detected_intent, entities, user_input, memory)
        if result == "__QUIT__":
            return "__QUIT__", detected_intent
        if result:
            return result, detected_intent

    return None, "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# AGENTIC TOOL-USE LOOP
# ═══════════════════════════════════════════════════════════════════════════════

AGENTIC_SYSTEM_PROMPT = """You are PANDA, an AI assistant that uses tools.

RULES:
1. Use short, natural sentences without robotic filler or emojis.
2. Only call tools when necessary. Do not guess results.
3. If the task is complete, stop calling tools and answer.

AVAILABLE TOOL:
- listen_to_user: Converts voice through mic to text. Use when asked to use voice/mic.

RESPONSE FORMAT:
To call a tool, respond ONLY with JSON: {"action": "listen_to_user", "parameters": {}}
Otherwise, respond in normal conversational text (do NOT wrap in JSON).
"""

def agentic_loop(user_input, conversation_history=None):
    """
    Agentic tool-use loop. Returns final text response, or None on failure.
    """
    import json

    messages = [{'role': 'system', 'content': AGENTIC_SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({'role': 'user', 'content': user_input})

    MAX_TOOL_ROUNDS = 5

    for _round in range(MAX_TOOL_ROUNDS):
        try:
            response = _ollama.chat(
                model=MODEL_NAME,
                messages=messages,
                options={"num_predict": 512, "temperature": 0.3},
            )
            raw = response['message']['content'].strip()
        except Exception as e:
            return f"⚠️ Agent brain error: {e}"

        tool_call = None
        try:
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "action" in parsed:
                tool_call = parsed
        except (json.JSONDecodeError, IndexError):
            pass

        if tool_call:
            action = tool_call["action"]
            params = tool_call.get("parameters", {})
            print(f"  \033[33m🔧 Agent calling tool: '{action}'\033[0m")
            tool_result = run_tool(action, **params)
            print(f"  \033[36m📦 Tool result: {tool_result}\033[0m")
            messages.append({'role': 'assistant', 'content': raw})
            messages.append({'role': 'user', 'content':
                f"Tool execution result:\n{json.dumps(tool_result, indent=2)}\n\n"
                f"Now use this result to continue. If the user spoke via voice, "
                f"treat the transcribed text as their new request and respond to it."
            })
            continue
        else:
            return raw

    return "⚠️ Agent loop exceeded maximum tool rounds. Please try again."


# ═══════════════════════════════════════════════════════════════════════════════
# LLM THINKING ENGINE  —  Mark V Primary Thinker
# ═══════════════════════════════════════════════════════════════════════════════

THINKING_ENGINE_PROMPT = """You are PANDA's decision core.
Decide the next action based on user input.

CRITICAL RULES:
1. **JSON ONLY**: Reply with ONLY valid JSON: {"action": "<name>", "params": {}}. No markdown or explanations.
2. **BACKGROUND MONITOR TIMELINE**: Answer questions about recent screen activity, opened windows, or typed keys directly using the respond action. Do NOT call vision tools (look, look_text, find, describe_screen).
3. **TOOL USE**: If no tool is needed (chat, questions, facts, jokes), select {"action": "respond", "params": {}}.
4. **TODO REMINDERS**: When using `todo_add`, dynamically infer `reminder_minutes_before` based on task importance (e.g., 15 mins for standard chores, 1440 mins/24h or more for projects/big milestones). If the task is complex/ambiguous and you are unsure when to remind, do NOT call the tool; instead select the 'respond' action and ask the user directly for clarification.

AVAILABLE TOOLS:
- execute_task      params: {"task": "description"}  - execute autonomous multi-step desktop task
- get_system_info   params: {}                       - CPU, RAM, disk status
- take_screenshot   params: {}
- look              params: {}                       - brief screen visual structure (do NOT use for history/timeline)
- look_text         params: {}                       - read screen text (do NOT use for history/timeline)
- find              params: {"target": "text/icon"}  - locate specific element
- describe_screen   params: {}                       - detailed screen description (do NOT use for history/timeline)
- timer             params: {"minutes": <number>}
- reminder          params: {"minutes": <number>, "message": "text"}
- todo_add          params: {"task": "description", "deadline": "YYYY-MM-DD HH:MM (optional)", "reminder_minutes_before": <number_of_minutes> (optional)}
- todo_show         params: {}
- todo_done         params: {"number": <number>}
- todo_remove       params: {"number": <number>}
- todo_clear        params: {}
- save_note         params: {"text": "note content"}
- show_notes        params: {}
- get_time          params: {}
- get_date          params: {}
- get_schedule      params: {}
- get_roadmap       params: {}
- goal_add          params: {"goal": "text"}
- goal_show         params: {}
- goal_complete     params: {"number": <number>}
- goal_plan          params: {"number": <number>}
- goal_progress      params: {"number": <number>}
- goal_step_done     params: {"goal": <number>, "step": <number>}
- goal_step_start    params: {"goal": <number>, "step": <number>}
- goal_next          params: {"number": <number>}
- goal_priority      params: {"number": <number>, "priority": <number>}
- goal_replan        params: {"number": <number>}
- goal_pause         params: {"number": <number>}
- goal_abandon       params: {"number": <number>}
- goal_history       params: {"number": <number>}
- project_add       params: {"name": "name", "description": "text"}
- project_show      params: {}
- preference_add    params: {"preference": "text"}
- preference_show   params: {}
- correction_add    params: {"mistake": "text", "correction": "text"}
- reflect           params: {}                       - consolidate memories, decay, learn from mistakes
- show_reflections  params: {}
- quit              params: {}
}
"""


def llm_thinking_engine(user_input: str, conversation_history=None, session_id=None) -> dict:
    """
    🧠 Mark V — LLM Thinking Engine (PRIMARY DECISION MAKER)

    The LLM reads user input + recent context and decides in one shot:
      - Which tool to call (returns type="tool")
      - Or to answer conversationally (returns type="respond")
      - On any failure, returns type="error" so the old SmartBrain can catch it

    Why this beats SmartBrain as the primary path:
      - Understands intent from meaning, not surface patterns
      - Handles ambiguity naturally ("chuck me the time" → get_time)
      - Adapts to context without rewriting regex rules
      - Adding new tools only requires updating this prompt

    What you're learning:
      - Structured LLM output (JSON routing) — the foundation of all modern agents
      - Low temperature (0.1) for deterministic routing decisions
      - Using only the last few conversation turns for routing (efficiency)
    """
    import json

    from personality import get_panda_persona

    system_prompt = get_panda_persona()

    # Inject recent background activity timeline & physical actions log
    try:
        import memory_manager
        sess_id = session_id or memory_manager.get_last_session_id()
        if sess_id:
            # 1. Screen Observations Timeline
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
                system_prompt += (
                    f"\n\n[RECENT BACKGROUND MONITOR ACTIVITY (TIMELINE, OLDEST TO NEWEST)]:\n"
                    f"{timeline_text}\n"
                )

            # 2. Physical Actions Log Timeline
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
                system_prompt += (
                    f"\n\n[RECENT PHYSICAL ACTIONS YOU (PANDA) TOOK (TIMELINE, OLDEST TO NEWEST)]:\n"
                    f"{action_text}\n"
                )

            system_prompt += (
                f"\n\nUse the screen observations timeline and your own physical actions log above to answer questions about what you or the user just did, opened, typed, or clicked. If the answer is present in these timelines, do NOT call any tool; instead, respond conversationally."
            )
    except Exception as e:
        pass

    messages = [
        {
            "role": "system",
            "content": system_prompt + "\n\n" + THINKING_ENGINE_PROMPT
        }
    ]

    # Provide recent context so the LLM handles follow-up messages correctly
    # e.g. "add that to my todo" after discussing a topic
    if conversation_history:
        messages.extend(conversation_history[-4:])   # last 4 turns is enough for routing

    messages.append({"role": "user", "content": user_input})

    try:
        response = _ollama.chat(
            model=MODEL_NAME,
            format="json",
            messages=messages,
            options={"num_predict": 128, "temperature": 0.1},  # low temp = consistent routing
        )
        raw = response["message"]["content"].strip()

        # Extract the JSON object robustly (finding first '{' and last '}')
        start_idx = raw.find('{')
        end_idx = raw.rfind('}')
        if start_idx != -1 and end_idx != -1:
            raw = raw[start_idx:end_idx+1]
        elif raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        action = parsed.get("action", "respond").strip()
        params = parsed.get("params", {})

        if action == "respond":
            return {"type": "respond", "action": "respond", "params": {}}

        return {"type": "tool", "action": action, "params": params}

    except json.JSONDecodeError:
        # LLM didn't return valid JSON → fall through to old SmartBrain
        return {"type": "error", "message": "Thinking engine returned invalid JSON."}
    except Exception as e:
        # Network/timeout/model error → fall through to old SmartBrain
        return {"type": "error", "message": f"Thinking engine failed: {e}"}


def handle_goal_add(params: dict, user_input: str, session_id: str) -> str:
    goal_text = params.get("goal", "").strip()
    if not goal_text:
        return "❌ Please provide a goal description."
    
    response_msg = f"✅ Goal added: '{goal_text}'"
    import vector_memory

    # Save to interactions and index in vector_memory to get an interaction_id
    interaction_id = vector_memory.save_turn_semantic(session_id, user_input, response_msg)

    # Save structured goal linked to this interaction
    vector_memory.save_goal_semantic(
        session_id=session_id,
        goal_text=goal_text,
        status='active',
        extracted_from=interaction_id,
        confidence=1.0
    )
    return response_msg


def handle_project_add(params: dict, user_input: str, session_id: str) -> str:
    name = params.get("name", "").strip()
    description = params.get("description", "").strip()
    if not name:
        return "❌ Please provide a project name."
    
    response_msg = f"✅ Project added: '{name}'"
    if description:
        response_msg += f" - {description}"
    
    import vector_memory

    # Save to interactions and index in vector_memory to get an interaction_id
    interaction_id = vector_memory.save_turn_semantic(session_id, user_input, response_msg)

    # Save structured project linked to this interaction
    vector_memory.save_project_semantic(
        session_id=session_id,
        project_name=name,
        description=description,
        extracted_from=interaction_id,
        confidence=1.0
    )
    return response_msg


def _summarize_entities_with_llm(entity_type: str, items: list) -> str | None:
    """Uses Ollama to generate a conversational summary of goals or preferences."""
    import os
    import json
    import ollama

    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")

    formatted_items = []
    for item in items:
        if entity_type == "goals":
            text = item.get("goal_text", "")
            mentions = item.get("mention_count", 1)
            formatted_items.append(f"- {text} (mentions: {mentions})")
        else:
            text = item.get("preference_text", "")
            mentions = item.get("mention_count", 1)
            formatted_items.append(f"- {text} (mentions: {mentions})")

    items_list_str = "\n".join(formatted_items)

    prompt = (
        f"You are PANDA, a helpful and warm AI assistant.\n"
        f"Aryan (the user) asked to see his {entity_type}.\n"
        f"Instead of showing a long, messy list of raw database records, write a friendly, conversational, and very concise summary of these {entity_type}.\n"
        f"CRITICAL: Write your response as a single continuous paragraph. NEVER use bullet points or numbered lists.\n"
        f"Focus more on the ones with higher mention counts (the most active/important ones).\n\n"
        f"Reply with ONLY the summary response, no preamble like 'Here is your summary:', and keep it to 2-3 sentences max."
    )

    try:
        client = ollama.Client(
            host=OLLAMA_URL,
            timeout=120.0,
            headers={"ngrok-skip-browser-warning": "true"}
        )
        response = client.chat(
            model=MODEL_NAME,
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.5, 'num_predict': 150}
        )
        return response['message']['content'].strip()
    except Exception as e:
        print(f"  [LLM Summary] Failed to generate conversational summary (non-fatal): {e}")
        return None


def handle_goal_show() -> str:
    import memory_manager
    import goal_engine
    goals = memory_manager.load_goals(status='active')
    if not goals:
        return "📋 You have no active goals."

    # Update dynamic priorities and ranks
    goals = goal_engine.prioritize_goals(goals)
    goals.sort(key=lambda x: x.get('priority', 5))

    # Keep top 5 items
    display_goals = goals[:5]

    # Attempt LLM summary
    summary = _summarize_entities_with_llm("goals", display_goals)
    if summary:
        return f"🎯 {summary}"

    # Graceful fallback to clean list box
    lines = ["╔══════════════════════════════════════╗",
             "║          🎯  ACTIVE GOALS            ║",
             "╚══════════════════════════════════════╝", ""]
    for idx, goal in enumerate(display_goals, 1):
        prog = f" (Progress: {goal['progress_pct']:.0%})" if goal.get('current_plan_version', 0) > 0 else ""
        lines.append(f"  {idx}. 🎯 {goal['goal_text']}{prog} (Mentions: {goal['mention_count']}, Priority: {goal['priority']})")
    return "\n".join(lines)


def _resolve_goal_index(number_param) -> dict | str:
    import memory_manager
    import goal_engine
    try:
        idx = int(number_param)
    except (ValueError, TypeError):
        return "❌ Please provide a valid goal number. Use 'show goals' first to see the list."
        
    goals = memory_manager.load_goals(status='active')
    if not goals:
        return "📋 You have no active goals."
        
    goals = goal_engine.prioritize_goals(goals)
    goals.sort(key=lambda x: x.get('priority', 5))
    
    if idx < 1 or idx > len(goals):
        return f"❌ Invalid goal number. You have {len(goals)} active goal(s)."
        
    return goals[idx - 1]


def handle_conversation_history(session_id: str) -> str:
    """Loads the recent conversation messages and returns a conversational recap."""
    import memory_manager
    messages = memory_manager.load_session_messages(session_id)
    if not messages:
        return "I don't have any record of our conversation in this session yet."
        
    recent = messages[-6:] # Get the last few turns
    history_lines = []
    for msg in recent:
        role = "Aryan" if msg["role"] == "user" else "PANDA"
        history_lines.append(f"{role}: {msg['content']}")
        
    formatted = "\n".join(history_lines)
    return f"Here is the recent conversation history from this session:\n\n{formatted}"


def handle_goal_plan(params: dict, session_id: str) -> str:
    goal_num = params.get("number")
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    import goal_engine
    import memory_manager
    
    goal_id = goal["id"]
    goal_text = goal["goal_text"]
    current_ver = goal.get("current_plan_version", 0)
    next_ver = (current_ver or 0) + 1
    
    steps = goal_engine.decompose_goal(goal_id, goal_text, next_ver)
    report = goal_engine.generate_progress_report(goal_id)
    return f"✅ Plan generated successfully!\n\n{report}"


def handle_goal_progress(params: dict) -> str:
    goal_num = params.get("number")
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    import goal_engine
    report = goal_engine.generate_progress_report(goal["id"])
    return report


def handle_goal_step_done(params: dict) -> str:
    goal_num = params.get("goal")
    step_num = params.get("step")
    
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    try:
        step_idx = int(step_num)
    except (ValueError, TypeError):
        return "❌ Please provide a valid step number."
        
    import memory_manager
    import goal_engine
    
    steps = memory_manager.load_goal_steps(goal["id"])
    if not steps:
        return "📋 This goal has no steps planned. Use 'plan goal <n>' first."
        
    target_step = next((s for s in steps if s["step_number"] == step_idx), None)
    if not target_step:
        return f"❌ Step {step_idx} not found for this goal. It has {len(steps)} steps."
        
    memory_manager.update_step_status(target_step["id"], "done")
    memory_manager.update_goal_progress(goal["id"])
    
    report = goal_engine.generate_progress_report(goal["id"])
    return f"🎉 Marked step {step_idx} of goal '{goal['goal_text']}' as done!\n\n{report}"


def handle_goal_step_start(params: dict) -> str:
    goal_num = params.get("goal")
    step_num = params.get("step")
    
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    try:
        step_idx = int(step_num)
    except (ValueError, TypeError):
        return "❌ Please provide a valid step number."
        
    import memory_manager
    import goal_engine
    
    steps = memory_manager.load_goal_steps(goal["id"])
    if not steps:
        return "📋 This goal has no steps planned. Use 'plan goal <n>' first."
        
    target_step = next((s for s in steps if s["step_number"] == step_idx), None)
    if not target_step:
        return f"❌ Step {step_idx} not found for this goal. It has {len(steps)} steps."
        
    memory_manager.update_step_status(target_step["id"], "in_progress")
    memory_manager.update_goal_progress(goal["id"])
    
    report = goal_engine.generate_progress_report(goal["id"])
    return f"🔄 Started step {step_idx} of goal '{goal['goal_text']}'!\n\n{report}"


def handle_goal_next(params: dict) -> str:
    goal_num = params.get("number")
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    import goal_engine
    import memory_manager
    
    next_step = goal_engine.suggest_next_action(goal["id"])
    if not next_step:
        steps = memory_manager.load_goal_steps(goal["id"])
        all_done = all(s["status"] == 'done' for s in steps) if steps else False
        if all_done:
            return f"🎉 Goal '{goal['goal_text']}' is fully complete! All steps are done."
        return f"📋 Goal '{goal['goal_text']}' has no next action step available (e.g. no steps planned)."
        
    steps = memory_manager.load_goal_steps(goal["id"])
    dep = next_step["depends_on"]
    if dep is not None:
        dep_step = next((x for x in steps if x["id"] == dep), None)
        if dep_step and dep_step["status"] != 'done':
            return f"❌ The next action for goal '{goal['goal_text']}' is step {next_step['step_number']}: '{next_step['step_text']}', but it is currently BLOCKED by step {dep_step['step_number']} ('{dep_step['step_text']}')."
            
    return f"🎯 Next action for goal '{goal['goal_text']}':\n👉 Step {next_step['step_number']}: '{next_step['step_text']}' (Status: {next_step['status']})"


def handle_goal_priority(params: dict) -> str:
    goal_num = params.get("number")
    priority_val = params.get("priority")
    
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    try:
        priority = int(priority_val)
        if priority < 1 or priority > 10:
            raise ValueError()
    except (ValueError, TypeError):
        return "❌ Please provide a valid priority number between 1 (highest) and 10 (lowest)."
        
    import memory_manager
    manual_weight = (11 - priority) / 10.0
    memory_manager.update_goal_priority(goal["id"], priority, manual_weight)
    
    return f"⭐ Set priority of goal '{goal['goal_text']}' to {priority} (manual boost weight: {manual_weight:.1f})."


def handle_goal_replan(params: dict, session_id: str) -> str:
    goal_num = params.get("number")
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    import goal_engine
    import memory_manager
    
    goal_id = goal["id"]
    goal_text = goal["goal_text"]
    current_ver = goal.get("current_plan_version", 0)
    next_ver = (current_ver or 0) + 1
    
    steps = goal_engine.decompose_goal(goal_id, goal_text, next_ver)
    report = goal_engine.generate_progress_report(goal_id)
    
    return f"🔄 Replanned goal successfully! Created plan v{next_ver} (preserved plan history).\n\n{report}"


def handle_goal_pause(params: dict) -> str:
    goal_num = params.get("number")
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    import memory_manager
    memory_manager.update_goal_status(goal["id"], "paused")
    return f"⏸️ Goal paused: '{goal['goal_text']}'. Urgency priority halved."


def handle_goal_abandon(params: dict) -> str:
    goal_num = params.get("number")
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    import memory_manager
    memory_manager.update_goal_status(goal["id"], "abandoned")
    return f"🗑️ Goal abandoned: '{goal['goal_text']}'. Soft-archived and excluded from active lists."


def handle_goal_history(params: dict) -> str:
    goal_num = params.get("number")
    goal = _resolve_goal_index(goal_num)
    if isinstance(goal, str):
        return goal
        
    import memory_manager
    history = memory_manager.load_goal_plan_history(goal["id"])
    if not history:
        return "📋 No plan history found for this goal."
        
    lines = [f"📜 Plan History for: '{goal['goal_text']}'", ""]
    for idx, plan in enumerate(history, 1):
        lines.append(f"  Version {plan['plan_version']} — Generated: {plan['generated_at']} (Model: {plan['model_used']})")
        steps = memory_manager.load_goal_steps(goal["id"], plan["plan_version"])
        for s in steps:
            status_char = "✅" if s["status"] == 'done' else ("🔄" if s["status"] == 'in_progress' else "⏳")
            lines.append(f"    {status_char} Step {s['step_number']}: {s['step_text']}")
        lines.append("")
        
    return "\n".join(lines)


def handle_project_show() -> str:
    import memory_manager
    projects = memory_manager.load_projects()
    if not projects:
        return "📋 You have no active projects."
    
    lines = ["╔══════════════════════════════════════╗",
             "║        🚀  ACTIVE PROJECTS           ║",
             "╚══════════════════════════════════════╝", ""]
    for idx, proj in enumerate(projects, 1):
        desc = f" - {proj['description']}" if proj['description'] else ""
        lines.append(f"  {idx}. 🚀 {proj['project_name']}{desc} (Mentions: {proj['mention_count']})")
    return "\n".join(lines)


def handle_goal_complete(params: dict) -> str:
    """Marks a goal as completed by its number (1-indexed from goal_show list)."""
    import memory_manager
    number = params.get("number", "")
    try:
        idx = int(number)
    except (ValueError, TypeError):
        return "❌ Please provide a goal number. Use 'show goals' first to see the list."
    
    goals = memory_manager.load_goals(status='active')
    if not goals:
        return "📋 You have no active goals to complete."
    if idx < 1 or idx > len(goals):
        return f"❌ Invalid goal number. You have {len(goals)} active goal(s)."
    
    goal = goals[idx - 1]
    memory_manager.update_goal_status(goal["id"], "completed")
    return f"🎉 Goal completed: '{goal['goal_text']}' — great work!"


def handle_preference_add(params: dict, user_input: str, session_id: str) -> str:
    pref_text = params.get("preference", "").strip()
    if not pref_text:
        return "❌ Please provide a preference."
    
    response_msg = f"✅ Preference recorded: '{pref_text}'"
    import vector_memory

    # Save to interactions and index in vector_memory to get an interaction_id
    interaction_id = vector_memory.save_turn_semantic(session_id, user_input, response_msg)

    # Save structured preference linked to this interaction
    vector_memory.save_preference_semantic(
        session_id=session_id,
        preference_text=pref_text,
        extracted_from=interaction_id,
        confidence=1.0
    )
    return response_msg


def handle_preference_show() -> str:
    import memory_manager
    preferences = memory_manager.load_preferences()
    if not preferences:
        return "📋 You have no recorded preferences."

    # Sort preferences by mention count descending, then ID descending
    preferences.sort(key=lambda x: (x.get('mention_count', 0), x.get('id', 0)), reverse=True)

    # Filter to preferences with mention_count >= 2
    high_mention_prefs = [p for p in preferences if p.get('mention_count', 0) >= 2]

    # Fallback to top 5 if none have >= 2, otherwise keep top 5 high-mention items to prevent clutter
    display_prefs = high_mention_prefs[:5] if high_mention_prefs else preferences[:5]

    # Attempt LLM summary
    summary = _summarize_entities_with_llm("preferences", display_prefs)
    if summary:
        return f"👤 {summary}"

    # Graceful fallback to clean list box
    lines = ["╔══════════════════════════════════════╗",
             "║        👤  USER PREFERENCES          ║",
             "╚══════════════════════════════════════╝", ""]
    for idx, pref in enumerate(display_prefs, 1):
        lines.append(f"  {idx}. 👤 {pref['preference_text']} (Mentions: {pref['mention_count']})")
    return "\n".join(lines)


def handle_correction_add(params: dict, user_input: str, session_id: str) -> str:
    mistake = params.get("mistake", "").strip()
    correction = params.get("correction", "").strip()
    if not mistake or not correction:
        return "❌ Please provide both the mistake and the correction."
    
    response_msg = f"✅ Memory corrected: Previously thought '{mistake}', but now I know '{correction}'."
    import vector_memory

    # Save to interactions and index in vector_memory to get an interaction_id
    interaction_id = vector_memory.save_turn_semantic(session_id, user_input, response_msg)

    # Save structured correction linked to this interaction
    vector_memory.save_correction_semantic(
        session_id=session_id,
        mistake_context=mistake,
        corrected_fact=correction,
        extracted_from=interaction_id,
        confidence=1.0
    )
    return response_msg


def handle_reflect() -> str:
    import reflection_engine
    print("  [ReflectionEngine] Triggered manual reflection...")
    new_refs = reflection_engine.generate_reflections("daily")
    merged_cnt = reflection_engine.consolidate_memories()
    rules_cnt = reflection_engine.learn_from_mistakes()
    decayed_cnt = reflection_engine.apply_memory_decay()
    
    summary = ["🧠 PANDA Reflection Complete:"]
    if new_refs:
        summary.append(f"  - Formed {len(new_refs)} new routine/habit insights.")
    else:
        summary.append("  - Gained no new routine insights (checked recent summaries).")
    if merged_cnt > 0:
        summary.append(f"  - Consolidated {merged_cnt} redundant memory goals/preferences.")
    if rules_cnt > 0:
        summary.append(f"  - Formed {rules_cnt} rules of action from mistakes.")
    if decayed_cnt > 0:
        summary.append(f"  - Decayed {decayed_cnt} inactive memory synapses.")
        
    return "\n".join(summary)


def handle_reflections_show() -> str:
    import memory_manager
    reflections = memory_manager.load_reflections()
    if not reflections:
        return "📋 PANDA has formed no reflections yet."
    
    lines = ["╔══════════════════════════════════════╗",
             "║        🧠  PANDA REFLECTIONS         ║",
             "╚══════════════════════════════════════╝", ""]
    # Group by category
    by_cat = {}
    for r in reflections:
        cat = r["category"].upper()
        by_cat.setdefault(cat, []).append(r)
        
    for cat, items in by_cat.items():
        lines.append(f" 📂 {cat}:")
        # Keep top 3 for each category to keep it neat
        items.sort(key=lambda x: x.get("importance_score", 0.5), reverse=True)
        for idx, item in enumerate(items[:3], 1):
            lines.append(f"   {idx}. ✨ {item['insight_text']} (Importance: {item['importance_score']:.2f})")
        lines.append("")
        
    return "\n".join(lines)


def handle_exit(session_id: str, memory):
    try:
        from vision import screen_monitor
        screen_monitor.stop_background_monitor()
    except Exception:
        pass

    try:
        from action import browser_controller
        browser_controller.close_browser()
    except Exception:
        pass

    bye_msg = "Goodbye, Aryan! See you next time!"
    print(f"  \033[35m✨ PANDA ❯\033[0m {bye_msg} 👋")
    print()
    
    # ── Sprint 5 Episodic Reflections ─────────────────────────────────────────
    # Run the reflection pipeline on a background thread so it can execute
    # while we play the goodbye audio and print the session summary.
    print(f"  \033[33m🧠 PANDA is reflecting on this session & consolidating memories...\033[0m")
    
    import threading
    import reflection_engine
    
    reflect_thread = threading.Thread(
        target=reflection_engine.run_reflection_pipeline,
        args=(session_id,),
        daemon=True
    )
    reflect_thread.start()
        
    voice.speak(bye_msg)
    _mic_listener = get_continuous_listener() if _PERCEPTION_AVAILABLE else None
    if _mic_listener and _mic_listener.is_running():
        _mic_listener.stop()
        
    print(f"  \033[33m📊 Session Summary:\033[0m")
    print(f"     Commands used: {memory.data['total_commands']}")
    final_achievements = memory.check_achievements()
    for ach in final_achievements:
        print(ach)
    print()
    print("  \033[36m  \"Sometimes you gotta run before you can walk.\" — Tony Stark\033[0m")
    print()
    
    # Wait for the background thread to finish writing to SQLite before we exit
    reflect_thread.join()


def _execute_tool_action(action: str, params: dict, user_input: str, memory, session_id: str) -> str | None:
    """
    Dispatch table: maps an action name (decided by the LLM) to the
    actual Python function that performs the work.

    Returns:
      - A string response to show/speak to the user
      - "__QUIT__" sentinel to trigger exit
      - None if action is unknown → caller falls through to panda_brain()

    What you're learning:
      - Dispatch table pattern: a dict of lambdas replaces a long if-elif chain
      - Same pattern used in compilers (opcode tables), game engines (event maps),
        and RPC systems (method registries)
      - Lambdas capture 'params' at call time — no state leaks between actions
    """
    import datetime as _dt
    from vision.vision_tools import handle_look, handle_look_text, handle_find, handle_describe_screen
    from action.action_tools import (
        handle_click, handle_right_click, handle_type, handle_press, handle_scroll, handle_drag,
        handle_browser_open, handle_browser_search, handle_browser_fill,
        handle_browser_click, handle_browser_scroll, handle_system_search,
        handle_select_and_copy
    )
    from action.task_executor import execute_autonomous_task

    def handle_execute_task(params: dict, user_input: str, session_id: str):
        from action.macro_planner import generate_macro_plan
        import voice
        
        task_desc = params.get("task", user_input)
        print(f"  \033[36m🧠 [Decomposer] Analyzing task: '{task_desc}'...\033[0m")
        
        plan = generate_macro_plan(task_desc)
        
        while plan.get("missing_variables"):
            missing = plan.get("missing_variables", [])
            question = plan.get("clarification_question")
            if not question:
                question = f"I need more details about: {', '.join(missing)}"
            print(f"  \033[35m✨ PANDA ❯\033[0m {question}")
            if hasattr(voice, "speak_blocking"):
                voice.speak_blocking(question)
            else:
                voice.speak(question)
            
            try:
                answer = input("  \033[36mYou ❯\033[0m ").strip()
            except EOFError:
                return "Task cancelled by user."
            
            ans_lower = answer.lower().strip()
            if any(w in ans_lower for w in ("cancel", "stop", "abort", "quit", "exit", "nevermind", "never mind", "don't send", "do not send", "forget it")):
                return "Task cancelled by user."
                
            task_desc += f"\nUser clarified: {answer}"
            print(f"  \033[36m🧠 [Decomposer] Re-evaluating milestones...\033[0m")
            plan = generate_macro_plan(task_desc)
            
        milestones = plan.get("milestones", [])
        print(f"  \033[36m✅ [Decomposer] Milestones locked: {milestones}\033[0m")
        return execute_autonomous_task(task_desc, session_id, milestones=milestones)


    _dispatch = {
        # ── Sprint 8 Actions ──────────────────────────────────────────────────
        "click":           lambda p: handle_click(p.get("target", ""), session_id),
        "right_click":     lambda p: handle_right_click(p.get("target", ""), session_id),
        "type":            lambda p: handle_type(p.get("text", ""), session_id),
        "press":           lambda p: handle_press(p.get("key", ""), session_id),
        "scroll":          lambda p: handle_scroll(p.get("direction", ""), session_id),
        "drag":            lambda p: handle_drag(p.get("source", ""), p.get("target", ""), session_id),
        "system_search":   lambda p: handle_system_search(p.get("query", ""), session_id),
        "browser_open":    lambda p: handle_browser_open(p.get("url", ""), session_id),
        "browser_search":  lambda p: handle_browser_search(p.get("query", ""), session_id),
        "browser_fill":    lambda p: handle_browser_fill(p.get("selector", ""), p.get("text", ""), session_id),
        "browser_click":   lambda p: handle_browser_click(p.get("selector", ""), session_id),
        "browser_scroll":  lambda p: handle_browser_scroll(p.get("direction", ""), session_id),
        "select_and_copy": lambda p: handle_select_and_copy(p.get("target", ""), session_id),

        # ── System ────────────────────────────────────────────────────────────
        "execute_task":    lambda p: handle_execute_task(p, user_input, session_id),
        "get_system_info": lambda p: get_system_info(),
        "take_screenshot": lambda p: take_screenshot(),
        # ── Study tools ───────────────────────────────────────────────────────
        "timer":           lambda p: start_timer(p.get("minutes", "")),
        "reminder":        lambda p: set_reminder(
                               p.get("minutes", ""), p.get("message", "")
                           ),
        "get_schedule":    lambda p: show_schedule(),
        # ── Tasks & Notes ─────────────────────────────────────────────────────
        "todo_add":        lambda p: add_todo(p.get("task", ""), p.get("deadline"), p.get("reminder_minutes_before")),
        "todo_show":       lambda p: show_todos(),
        "todo_done":       lambda p: complete_todo(p.get("number", "")),
        "todo_remove":     lambda p: remove_todo(p.get("number", "")),
        "todo_clear":      lambda p: clear_completed(),
        "save_note":       lambda p: save_note(p.get("text", "")),
        "show_notes":      lambda p: show_notes(),
        # ── Sprint 2 Structured Entities ──────────────────────────────────────
        "goal_add":        lambda p: handle_goal_add(p, user_input, session_id),
        "goal_show":       lambda p: handle_goal_show(),
        "goal_complete":   lambda p: handle_goal_complete(p),
        "goal_plan":        lambda p: handle_goal_plan(p, session_id),
        "goal_progress":    lambda p: handle_goal_progress(p),
        "goal_step_done":   lambda p: handle_goal_step_done(p),
        "goal_step_start":  lambda p: handle_goal_step_start(p),
        "goal_next":        lambda p: handle_goal_next(p),
        "goal_priority":    lambda p: handle_goal_priority(p),
        "goal_replan":      lambda p: handle_goal_replan(p, session_id),
        "goal_pause":       lambda p: handle_goal_pause(p),
        "goal_abandon":     lambda p: handle_goal_abandon(p),
        "goal_history":     lambda p: handle_goal_history(p),
        "project_add":     lambda p: handle_project_add(p, user_input, session_id),
        "project_show":    lambda p: handle_project_show(),
        # ── Sprint 3 Learning & Identity ──────────────────────────────────────
        "preference_add":  lambda p: handle_preference_add(p, user_input, session_id),
        "preference_show": lambda p: handle_preference_show(),
        "correction_add":  lambda p: handle_correction_add(p, user_input, session_id),
        # ── Sprint 5 Episodic Reflections ─────────────────────────────────────
        "reflect":         lambda p: handle_reflect(),
        "show_reflections": lambda p: handle_reflections_show(),
        # ── Vision (3-layer stack: UI Automation → OCR → OpenCV) ─────────────
        "look":            lambda p: handle_look(session_id),
        "look_text":       lambda p: handle_look_text(session_id),
        "find":            lambda p: handle_find(
                               p.get("target") or p.get("query") or p.get("element", ""),
                               session_id
                           ),
        "describe_screen": lambda p: handle_describe_screen(session_id),
        # ── History ───────────────────────────────────────────────────────────
        "get_history":     lambda p: handle_conversation_history(session_id),
        "show_history":    lambda p: handle_conversation_history(session_id),
        # ── Basics ────────────────────────────────────────────────────────────
        "get_time":        lambda p: f"🕐 It's {_dt.datetime.now().strftime('%I:%M %p')}",
        "get_date":        lambda p: f"📅 Today is {_dt.datetime.now().strftime('%A, %B %d, %Y')}",
        "get_roadmap":     lambda p: get_roadmap(),
        # ── Control ───────────────────────────────────────────────────────────
        "quit":            lambda p: "__QUIT__",
    }

    handler = _dispatch.get(action)
    if handler:
        return handler(params)
    return None   # Unknown action → caller will fall through to panda_brain()


import requests
from urllib.parse import urlparse

def ensure_ollama_running():

    parsed = urlparse(OLLAMA_URL)
    is_remote = parsed.hostname not in ("localhost", "127.0.0.1")

    try:

        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=15,
            headers={
                "ngrok-skip-browser-warning": "true",
                "User-Agent": "PANDA-V4"
            }
        )

        response.raise_for_status()

        data = response.json()
        models = [m.get("name") for m in data.get("models", [])]
        
        print(f"✅ Brain online at: {OLLAMA_URL}")
        
        # Exact match or base match (e.g., if MODEL_NAME is 'llama3.1:8b' but only 'llama3.1' or 'llama3.1:latest' exists)
        # Ollama often normalizes tags, so we should do a flexible check or just warn if it's completely missing.
        model_found = False
        for m in models:
            if m == MODEL_NAME or m.startswith(MODEL_NAME.split(":")[0]):
                model_found = True
                break
                
        if not model_found:
            print(f"\n⚠️  WARNING: The model '{MODEL_NAME}' does not appear to be installed on the Ollama server!")
            print(f"   Available models: {', '.join(models) if models else 'None'}")
            print(f"   You may need to run: ollama pull {MODEL_NAME}\n")
            
        return True

    except Exception as e:

        if is_remote:
            print(f"\n⚠️ Cloud brain at {OLLAMA_URL} is not reachable!")
            print("   Make sure your Colab notebook is running and the Ngrok tunnel is active.\n")
        else:
            print("\n⚠️ Local Ollama server is not running!\n")

        print(f"DEBUG ERROR: {e}")

        return False



# ═══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """
    The main event loop.

    Input sources:
      • Text:  blocking input() — used when mic is OFF
      • Voice: ContinuousListener queue — used when mic is ON (voice in)
      • Voice: one-shot listen_to_user() — used when user types 'voice'

    Output:
      • Text:  printed to terminal
      • Voice: Piper TTS via voice.speak() / voice.speak_streaming()
                Interrupted mid-sentence when ContinuousListener detects speech
    """
    # Set Windows DPI Scaling awareness to prevent coordinate drift on high-res displays
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    if not ensure_ollama_running():
        print("❌ Cannot proceed without Ollama brain. Exiting.")
        sys.exit(1)

    # ── Brain state layer: manages sessions, context, trimming, filtering ──
    conv_manager = ConversationManager()
    conv_manager.initialize()

    try:
        from task_manager import start_deadline_checker
        start_deadline_checker()
    except Exception as e:
        print(f"⚠️ [Startup] Failed to start deadline checker: {e}")

    # Start background screen and input activity monitor
    try:
        from vision import screen_monitor
        screen_monitor.start_background_monitor(conv_manager.get_session_id())
    except Exception as e:
        print(f"⚠️ [Startup] Failed to start screen monitor: {e}")

    brain  = SmartBrain()
    memory = PandaMemory()

    # Grab the shared ContinuousListener singleton (not started yet)
    _mic_listener = get_continuous_listener() if _PERCEPTION_AVAILABLE else None

    print(BANNER)
    print(memory.get_welcome_message())
    print()

    new_achievements = memory.check_achievements()
    for ach in new_achievements:
        print(ach)
    if new_achievements:
        print()

    # Step 13: Startup restoration — tell user what we discussed last time
    last_context = conv_manager.get_startup_context()
    if last_context:
        startup_msg = f"Welcome back, Sir! {last_context}. How shall we continue?"
    else:
        startup_msg = "Online and operational. How may I assist you today, Sir?"
    print(f"  \033[35m✨ PANDA ❯\033[0m {startup_msg} ✨")
    print()
    if hasattr(voice, "speak_blocking"):
        voice.speak_blocking(startup_msg)
    else:
        voice.speak(startup_msg)

    # ─── Main Loop ────────────────────────────────────────────────────
    while True:
        try:
            # ── Get input — from mic queue or keyboard ─────────────────
            if _mic_listener and _mic_listener.is_running():
                # Continuous mic mode: drain queue with a short timeout so
                # Ctrl+C still works. If nothing arrives, loop again.
                try:
                    user_input = _mic_listener.text_queue.get(timeout=0.2)
                    # ───────────── COMMENTED OUT PENDING CONTEXT FOR REGEX/FSM NLU ─────────────
                    # if memory.data.get("pending"):
                    #     pending = memory.data["pending"]
                    # 
                    #     # Cancel words abort the slot-fill
                    #     if user_input.strip().lower() in _CANCEL_WORDS:
                    #         result = _fsm_cancel()
                    #         memory.data["pending"] = None
                    #         print(f"  \033[35m✨ PANDA ❯\033[0m {result['message']}")
                    #         voice.speak(result["message"])
                    #         continue
                    # 
                    #     new_entities = extract_entities(user_input, pending["action"])
                    # 
                    #     if new_entities:
                    #         pending["data"].update(new_entities)
                    # 
                    #     decision_fusion = fuse(
                    #         pending["action"],
                    #         pending["data"],
                    #         user_input
                    #     )
                    # 
                    #     if decision_fusion["status"] == "missing":
                    #         print(f"  \033[35m✨ PANDA ❯\033[0m {decision_fusion['message']}")
                    #         continue
                    # 
                    #     elif decision_fusion["status"] == "cancelled":
                    #         memory.data["pending"] = None
                    #         print(f"  \033[35m✨ PANDA ❯\033[0m {decision_fusion['message']}")
                    #         voice.speak(decision_fusion["message"])
                    #         continue
                    # 
                    #     elif decision_fusion["status"] == "error":
                    #         memory.data["pending"] = None
                    #         print(f"  \033[35m✨ PANDA ❯\033[0m {decision_fusion['message']}")
                    #         voice.speak(decision_fusion["message"])
                    #         continue
                    # 
                    #     elif decision_fusion["status"] == "ready":
                    #         response = _execute_tool_action(
                    #             decision_fusion["action"],
                    #             decision_fusion["data"],
                    #             user_input,
                    #             memory,
                    #             conv_manager.get_session_id()
                    #         )
                    # 
                    #         memory.data["pending"] = None
                    # 
                    #         print(f"  \033[35m✨ PANDA ❯\033[0m {response}")
                    #         voice.speak(response)
                    #         continue
                    # ───────────────────────────────────────────────────────────────────────────
                    print(f"  \033[36m🎤 You said:\033[0m {user_input}")
                    print()
                except queue.Empty:
                    continue
            else:
                user_input = input("  \033[32mYou ❯\033[0m ").strip()

            if not user_input:
                continue

            # ─── INLINE VOICE IN / OUT — handled before NLU ───────────
            user_lower = user_input.lower().strip()

            if user_lower.startswith("search memory "):
                query = user_input[14:].strip()
                if query:
                    import vector_memory
                    print(f"  \033[33m🔎 Searching vector memory for: '{query}'...\033[0m")
                    results_search = vector_memory.semantic_search(query, top_k=3)
                    if results_search:
                        print()
                        for idx, res in enumerate(results_search):
                            print(f"    {idx+1}. Similarity: {res['similarity']:.4f} | Importance: {res['importance_score']:.2f}")
                            print(f"       User: '{res['user_message']}'")
                            print(f"       Bot:  '{res['assistant_response']}'")
                            print(f"       Score: {res['score']:.4f} | Session: {res['session_id']}")
                            print()
                    else:
                        print("    No relevant semantic memories found.")
                else:
                    print("  ❌ Please provide a search query. Usage: search memory <query>")
                print()
                continue

            if user_lower == "test rag":
                import memory_manager
                stats = memory_manager.get_db_stats()
                cnt_int = stats["interactions_count"]
                cnt_vec = stats["vector_memory_count"]
                print(f"  \033[33m🧠 PANDA RAG Status:\033[0m")
                print(f"     Total Interactions: {cnt_int}")
                print(f"     Total Vector Embeddings: {cnt_vec}")
                if cnt_int > 0:
                    import vector_memory
                    test_query = "career goals"
                    print(f"     Running test query: '{test_query}'...")
                    results_search = vector_memory.semantic_search(test_query, top_k=1)
                    if results_search:
                        res = results_search[0]
                        print(f"     Best Match: Similarity: {res['similarity']:.4f}")
                        print(f"       User: '{res['user_message']}'")
                        print(f"       Bot:  '{res['assistant_response']}'")
                print()
                continue

            if user_lower in ("voice in", "mic on", "start listening"):
                if _mic_listener:
                    msg = _mic_listener.start()
                else:
                    msg = "❌ Mic not available. Install faster-whisper and pyaudio."
                print(f"  \033[35m✨ PANDA ❯\033[0m {msg}")
                print()
                continue

            if user_lower in ("voice out", "mic off", "stop listening"):
                if _mic_listener:
                    msg = _mic_listener.stop()
                else:
                    msg = "🔇 Mic is not running."
                print(f"  \033[35m✨ PANDA ❯\033[0m {msg}")
                print()
                continue

            # ─── SINGLE-SHOT VOICE INPUT ──────────────────────────────
            # User typed "voice" / "listen" → record one utterance, then
            # process the transcript as if they had typed it.
            if user_lower in ("voice", "listen", "speak"):
                result = _listen_once()
                if result["status"] == "success":
                    transcribed = result["text"]
                    print(f"  \033[36m🎤 You said:\033[0m {transcribed}")
                    print()
                    user_input = transcribed
                else:
                    print(f"  \033[31m❌ Voice error:\033[0m {result['message']}")
                    print()
                    continue

            # ─── Step 1: Check Easter Eggs ─────────────────────────────
            print()
            easter_egg = check_easter_egg(user_input)
            if easter_egg:
                print(f"  \033[35m✨ PANDA ❯\033[0m {easter_egg}")
                voice.speak(easter_egg)
                memory.record_command("easter_egg")
                print()
                continue

            # ─── COMMENTED OUT SLOT-FILL & FSM BYPASS FOR REGEX/FSM NLU ─────────
            # # ─── Cancel: abort an active slot-fill conversation ───────────
            # if _fsm_state() == "awaiting_slot" and user_lower in _CANCEL_WORDS:
            #     result = _fsm_cancel()
            #     print(f"  \033[35m✨ PANDA ❯\033[0m {result['message']}")
            #     voice.speak(result["message"])
            #     print()
            #     continue
            # 
            # # ─── FSM AWAITING_SLOT bypass ─────────────────────────────────
            # # The user is answering PANDA's slot question ("when?" / "what?").
            # # Sending this to the LLM thinking engine would misroute it as a
            # # brand-new command.  Instead, feed it directly to entity_extractor
            # # + fuse() so the FSM can merge the answer and advance.
            # if _fsm_state() == "awaiting_slot":
            #     pending_intent  = _fsm_pending_intent()
            #     slot_entities   = extract_entities(user_input, pending_intent)
            #     decision_fusion = fuse(pending_intent, slot_entities, user_input)
            # 
            #     if decision_fusion["status"] == "missing":
            #         msg = decision_fusion["message"]
            #         print(f"  \033[35m✨ PANDA ❯\033[0m {msg}")
            #         voice.speak(msg)
            #         print()
            #         continue
            # 
            #     elif decision_fusion["status"] == "error":
            #         msg = decision_fusion["message"]
            #         print(f"  \033[35m✨ PANDA ❯\033[0m {msg}")
            #         voice.speak(msg)
            #         print()
            #         continue
            # 
            #     elif decision_fusion["status"] == "ready":
            #         response = _execute_tool_action(
            #             decision_fusion["action"],
            #             decision_fusion["data"],
            #             user_input,
            #             memory,
            #             conv_manager.get_session_id()
            #         )
            #         if response:
            #             for line in response.split("\n"):
            #                 if line.strip():
            #                     print(f"  \033[35m✨ PANDA ❯\033[0m {line}")
            #                 else:
            #                     print()
            #             voice.speak(response)
            #             memory.record_command(decision_fusion["action"])
            #         print()
            #         continue
            # ────────────────────────────────────────────────────────────────────

            # ─── Step 2 [NEW — MARK V]: LLM Thinking Engine — PRIMARY ────
            # 🧠 The LLM now decides what PANDA should do.
            # It gets: user input + last few conversation turns.
            # It returns: a tool call (JSON) OR {"action": "respond"}.
            # Old SmartBrain steps are PRESERVED below as a safety fallback —
            # they only run if llm_thinking_engine() returns type="error".
            print(f"\033[2K  \033[33m🧠 Thinking...\033[0m", end="\r", flush=True)
            decision = llm_thinking_engine(user_input, conv_manager.get_context(), conv_manager.get_session_id())

            if decision["type"] == "tool":
                # ── LLM wants to run a tool ─────────────────────────────────
                action = decision["action"]
                params = decision["params"]
                print(f"  \033[33m🧠 LLM → tool: '{action}'\033[0m")
                # ── COMMENTED OUT OLD REGEX/FSM NLU ROUTING ────────────────
                # extra_entities = extract_entities(user_input, action)
                # 
                # if extra_entities:
                #     params.update(extra_entities)
                # 
                # # ───────────── FUSION LAYER ─────────────
                # decision_fusion = fuse(action, params, user_input)
                # 
                # # ───────────── DECISION HANDLING ─────────────
                # if decision_fusion["status"] == "missing":
                #     response = decision_fusion["message"]
                # 
                # elif decision_fusion["status"] == "cancelled":
                #     response = decision_fusion["message"]
                # 
                # elif decision_fusion["status"] == "error":
                #     response = decision_fusion["message"]
                #     memory.data["pending"] = None
                # 
                # elif decision_fusion["status"] == "ready":
                #     response = _execute_tool_action(
                #         decision_fusion["action"],
                #         decision_fusion["data"],
                #         user_input,
                #         memory,
                #         conv_manager.get_session_id()
                #     )
                # 
                #     #Clear pending
                #     memory.data["pending"] = None
                # ───────────────────────────────────────────────────────────

                # Direct tool execution bypasses old NLU FSM completely
                response = _execute_tool_action(
                    action,
                    params,
                    user_input,
                    memory,
                    conv_manager.get_session_id()
                )

                if response == "__QUIT__":
                    handle_exit(conv_manager.get_session_id(), memory)
                    break

                elif response:
                    for line in response.split("\n"):
                        if line.strip():
                            print(f"  \033[35m✨ PANDA ❯\033[0m {line}")
                        else:
                            print()
                    voice.speak(response)
                    # Sync tool results to conversation context so the LLM knows
                    # what just happened (e.g. "I added a goal to become CEO")
                    conv_manager.save_turn(user_input, response)
                    memory.record_command(action)
                    new_achievements = memory.check_achievements()
                    if new_achievements:
                        print()
                        for ach in new_achievements:
                            print(ach)

                else:
                    # Dispatch table returned None (unknown action) — stream a reply
                    print(f"  \033[35m✨ PANDA ❯\033[0m ", end="", flush=True)
                    reply = _stream_and_collect(
                        panda_brain(user_input, conversation_history=conv_manager.get_context(), session_id=conv_manager.get_session_id())
                    )
                    conv_manager.save_turn(user_input, reply)
                    memory.record_command("llm_chat")

                print()
                continue

            elif decision["type"] == "respond":
                # ── LLM decided: pure conversation, no tool needed ──────────
                print(f"  \033[35m✨ PANDA ❯\033[0m ", end="", flush=True)
                reply = _stream_and_collect(
                    panda_brain(user_input, conversation_history=conv_manager.get_context(), session_id=conv_manager.get_session_id())
                )
                conv_manager.save_turn(user_input, reply)
                memory.record_command("llm_chat")
                print()
                continue

            # ══════════════════════════════════════════════════════════════════
            # [OLD BRAIN — DEMOTED TO SAFETY FALLBACK]
            # ⚠️  Code below runs ONLY if llm_thinking_engine() returned
            #     type="error" (Ollama down, JSON parse failure, etc.).
            #
            # Mark V: SmartBrain is no longer the primary thinker.
            # It is preserved here as a reliability safety net.
            # Mark VI will remove it once the new engine proves stable.
            # ══════════════════════════════════════════════════════════════════

            if decision["type"] == "error":
                print(f"  \033[31m⚠️  Thinking engine error ({decision.get('message', 'Unknown')}) — falling back directly to conversational LLM\033[0m")
                print(f"  \033[35m✨ PANDA ❯\033[0m ", end="", flush=True)
                reply = _stream_and_collect(
                    panda_brain(user_input, conversation_history=conv_manager.get_context(), session_id=conv_manager.get_session_id())
                )
                conv_manager.save_turn(user_input, reply)
                memory.record_command("llm_chat")
                print()
                continue

            # ==================================================================
            # [COMMENTED OUT REGEX/EMBEDDING NLU ARCHITECTURE FALLBACK]
            #
            # # ─── Step 3 [demoted]: Is it a question? → straight to Venessa ──
            # if _is_question(user_input, has_conversation_history=bool(conv_manager.get_context())):
            #     print(f"  \033[35m✨ PANDA\033[0m ", end="", flush=True)
            #     reply = _stream_and_collect(
            #         panda_brain(user_input, conversation_history=conv_manager.get_context())
            #     )
            #     conv_manager.save_turn(user_input, reply)
            #     memory.record_command("llm_chat")
            #     print()
            #     continue
            #
            # # ─── Step 4 [demoted]: Smart Brain NLU ───────────────────────────
            # result = brain.process(user_input)
            #
            # if result:
            #     intent     = result["intent"]
            #     entities   = result["entities"]
            #     method     = result["method"]
            #     confidence = result["confidence"]
            #
            #     # Safety: quit must only fire on exact typed words
            #     if method in ("embedding", "llm_fallback") and intent == "quit":
            #         intent = None
            #
            #     if intent:
            #         if method == "embedding":
            #             print(f"  \033[33m🔗 Embedding → '{intent}' ({confidence})\033[0m")
            #         elif method == "llm_fallback":
            #             print(f"  \033[33m🤖 LLM fallback → '{intent}'\033[0m")
            #
            #         response = handle_intent(intent, entities, user_input, memory)
            #
            #         if response == "__QUIT__":
            #             handle_exit(conv_manager.get_session_id(), memory)
            #             break
            #
            #         elif response:
            #             for line in response.split("\n"):
            #                 if line.strip():
            #                     print(f"  \033[35m✨ PANDA ❯\033[0m {line}")
            #                 else:
            #                     print()
            #             voice.speak(response)
            #
            #         else:
            #             # Intent matched but handler returned None → Venessa
            #             print(f"  \033[35m✨ PANDA ❯\033[0m ", end="", flush=True)
            #             reply = _stream_and_collect(
            #                 panda_brain(user_input, conversation_history=conv_manager.get_context())
            #             )
            #             conv_manager.save_turn(user_input, reply)
            #             memory.record_command("llm_chat")
            #
            #         memory.record_command(intent)
            #         new_achievements = memory.check_achievements()
            #         if new_achievements:
            #             print()
            #             for ach in new_achievements:
            #                 print(ach)
            #
            #     else:
            #         # Intent nullified (e.g. unsafe quit via embedding) → Venessa
            #         print(f"  \033[35m✨ PANDA ❯\033[0m ", end="", flush=True)
            #         reply = _stream_and_collect(
            #             panda_brain(user_input, conversation_history=conv_manager.get_context())
            #         )
            #         conv_manager.save_turn(user_input, reply)
            #         memory.record_command("llm_chat")
            #
            # else:
            #     # ─── Step 5 [demoted]: Agentic tool-use fallback ──────────────
            #     agent_response = agentic_loop(
            #         user_input,
            #         conversation_history=conv_manager.get_context()
            #     )
            #     if agent_response:
            #         print(f"  \033[35m✨ PANDA ❯\033[0m {agent_response}")
            #         voice.speak(agent_response)
            #         conv_manager.save_turn(user_input, agent_response)
            #     else:
            #         print(f"  \033[35m✨ PANDA ❯\033[0m ", end="", flush=True)
            #         reply = _stream_and_collect(
            #             panda_brain(user_input, conversation_history=conv_manager.get_context())
            #         )
            #         conv_manager.save_turn(user_input, reply)
            #     memory.record_command("llm_chat")
            #
            # print()
            # ==================================================================

        except KeyboardInterrupt:
            print("\n")
            print(f"  \033[35m✨ PANDA ❯\033[0m Caught Ctrl+C! Use 'quit' to exit properly. 😉")
            print()

        except Exception as e:
            print(f"\n  \033[31m❌ Something went wrong: {e}\033[0m")
            print(f"  \033[33m   Don't worry, PANDA is still running! Try again.\033[0m")
            print()


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()