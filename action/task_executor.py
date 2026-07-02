"""
PANDA — Task Executor (Decomposed Architecture)
=================================================
The milestone-driven execution engine.

Architecture:
  1. Receives a flat list of milestone strings from the Decomposer
  2. Processes milestones sequentially using a Python-managed queue
  3. For each milestone, runs an OODA loop with the Actor LLM
  4. Implements per-milestone retry_count with Home Base Reset
  5. Supports speculative action batching for safe sequential actions
  6. HITL gatekeeping for destructive actions

Features:
  - Milestone stack managed in Python (not by LLM)
  - Per-milestone retry counter with Home Base Reset after 3 failures
  - Logical compensation (re-routing) on action failures
  - HITL destructive action gatekeeping
  - Speculative action batching for latency reduction
  - Loop detection and action blacklisting
"""

import os
import json
import time
import ollama
from dotenv import load_dotenv
from action import action_executor
from action import action_tools
from action.task_prompts import get_actor_system_prompt

load_dotenv()

def print(*args, **kwargs):
    """Custom print wrapper that prevents UnicodeEncodeError on Windows terminal."""
    import sys
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    file = kwargs.get('file', sys.stdout)
    
    text = sep.join(str(arg) for arg in args)
    try:
        file.write(text + end)
        file.flush()
    except UnicodeEncodeError:
        try:
            enc = file.encoding or 'utf-8'
            file.write(text.encode(enc, errors='replace').decode(enc) + end)
            file.flush()
        except Exception:
            try:
                file.write(text.encode('ascii', errors='replace').decode('ascii') + end)
                file.flush()
            except Exception:
                pass

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")

_client = ollama.Client(host=OLLAMA_URL, headers={"ngrok-skip-browser-warning": "true"})

# ── Constants ────────────────────────────────────────────────────────────────
MAX_STEPS_PER_MILESTONE = 10    # Hard limit per milestone before Home Base Reset
MAX_MILESTONE_RESETS = 2        # Max Home Base Resets per milestone
MAX_RETRIES_BEFORE_RESET = 3   # Consecutive failures before triggering Home Base Reset
TOTAL_HARD_LIMIT = 40           # Absolute max steps across all milestones
SOFT_LIMIT = 20                 # Soft limit — ask user to continue


# ── Screen Capture ───────────────────────────────────────────────────────────

def _capture_screen_with_retry(session_id: str, retries: int = 3):
    """Safely capture the screen state."""
    from vision.screen_state import build_screen_state
    for attempt in range(retries):
        try:
            return build_screen_state(session_id)
        except Exception as e:
            if attempt == retries - 1:
                return {"error": str(e), "summary": "Failed to capture screen"}
            time.sleep(1)


# ── Rich Context Builder ────────────────────────────────────────────────────

def build_rich_task_context(task_description: str, session_id: str) -> str:
    """Builds a rich context block containing current date/time, user preferences, and recent screen history."""
    import datetime
    import memory_manager
    
    # 1. Date and Time
    now = datetime.datetime.now()
    datetime_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
    
    # 2. User Preferences
    prefs_list = []
    try:
        preferences = memory_manager.load_preferences()
        for p in preferences:
            if not p.get("consolidated_to"):
                text = p.get("preference_text")
                if text:
                    prefs_list.append(f"- {text}")
    except Exception as e:
        prefs_list.append(f"(Error loading preferences: {e})")
        
    prefs_str = "\n".join(prefs_list) if prefs_list else "- No saved preferences."
    
    # 3. Recent Screen Observations (Activity History)
    obs_list = []
    try:
        observations = memory_manager.get_recent_observations(session_id, limit=8)
        observations.reverse()  # Show chronologically
        for obs in observations:
            t_str = obs.get("created_at", "")
            if "T" in t_str:
                t_str = t_str.split("T")[1][:8]
            obs_list.append(f"[{t_str}] Active Window: '{obs.get('active_window')}' | Activity: {obs.get('observation_text')}")
    except Exception as e:
        obs_list.append(f"(Error loading screen observations: {e})")
        
    obs_str = "\n".join(obs_list) if obs_list else "- No recent screen activity logged."
    
    context = f"""==================================================
CURRENT ENVIRONMENT & USER PROFILE CONTEXT
==================================================
Current Date/Time: {datetime_str}

User Profile & Preferences:
{prefs_str}

Recent Screen Activity History (Window switches, clicks, typing):
{obs_str}
=================================================="""
    return context


# ── User Feedback & Post-Mortem ──────────────────────────────────────────────

def _extract_and_save_user_preference(feedback: str, session_id: str):
    """
    Extracts atomic preferences from user feedback using LLM and saves them to database.
    """
    import memory_manager
    if not feedback or feedback.strip().lower() in ("nothing", "none", "no", "n", "good job", "thanks", "thank you", "perfect"):
        return
        
    print("🧠 [PANDA] Analyzing feedback to extract preferences...")
    
    system_prompt = """You are PANDA's User Preference Extractor.
Identify if the user is specifying any preferences, instructions, or rules for future tasks (e.g. "always use right click", "never close Chrome", "don't search the start menu").

CRITICAL GENERALIZATION RULE:
If the user's preference mentions a specific application (e.g. AnyDesk, Notepad, Chrome, etc.), you must GENERALIZE it so it applies to ALL desktop applications or general software of the same type.
- Example: If the user says "don't relaunch AnyDesk", distill it to: "Do not relaunch native desktop applications if they are already open."
- Example: If the user says "do not use browser_fill for AnyDesk", distill it to: "Do not use browser-specific actions (like browser_fill or browser_click) on native desktop applications."

If the user specifies a preference, distill it into a clean, concise, atomic generalized rule.
If there are multiple preferences, list them separated by newlines.
If the feedback contains no actionable preference or rule, output nothing.
Output ONLY the distilled preference rules, or nothing if none are found. Do NOT add preamble or conversational text."""
    
    try:
        response = _client.chat(
            model=MODEL_NAME,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"USER FEEDBACK: {feedback}"}
            ],
            options={"temperature": 0.0}
        )
        pref_text = response['message']['content'].strip()
        if pref_text:
            lines = [line.strip() for line in pref_text.split("\n") if line.strip()]
            for line in lines:
                clean_pref = line
                if clean_pref.startswith("- "):
                    clean_pref = clean_pref[2:]
                elif clean_pref.startswith("* "):
                    clean_pref = clean_pref[2:]
                
                # Reject raw JSON blobs — only save natural language preferences
                if clean_pref.startswith("{") or clean_pref.startswith("["):
                    print(f"⚠️ [PANDA] Skipping malformed preference (raw JSON): {clean_pref[:60]}")
                    continue
                
                print(f"💡 [PANDA] Extracted preference: {clean_pref}")
                memory_manager.save_preference(session_id, clean_pref)
    except Exception as e:
        print(f"⚠️ [PANDA] Failed to extract preferences: {e}")


def _generate_post_mortem(goal: str, trajectory_history: list, session_id: str):
    """
    Analyzes the execution history to extract a lesson learned if mistakes occurred,
    and saves it to memory_manager.
    """
    import memory_manager
    
    print("🧠 [PANDA] Analyzing trajectory to distill lessons learned...")
    
    system_prompt = """You are PANDA's Post-Mortem Lesson Distiller.
Analyze the execution history of PANDA attempting to achieve a goal.
Identify what mistakes were made (e.g., repeating failed actions, using wrong tools, hallucinating screen components, clicking wrong coordinates).
Distill one or two CONCISE, GENERAL lessons for the future to prevent these mistakes.

CRITICAL GENERALIZATION RULE:
If the lesson is specific to a particular application, generalize it so it applies to ALL desktop applications or software of the same type (e.g. instead of writing "When using AnyDesk, do X", write "When using native desktop applications, do X").

Format your response as a simple text summary of the lesson (1-2 sentences maximum, e.g. "When copying text from a window, use right-click on the text instead of search tools.").
Avoid listing steps; focus only on the generalized rule or lesson."""
    
    user_prompt = f"""GOAL: {goal}
EXECUTION HISTORY:
{json.dumps(trajectory_history, indent=2)}

Please distill the lesson learned:"""
    
    try:
        response = _client.chat(
            model=MODEL_NAME,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            options={"temperature": 0.2}
        )
        lesson_text = response['message']['content'].strip()
        if lesson_text:
            # Reject raw JSON blobs — only save natural language lessons
            if lesson_text.startswith("{") or lesson_text.startswith("["):
                print(f"⚠️ [PANDA] Skipping malformed lesson (raw JSON): {lesson_text[:60]}")
            else:
                print(f"💡 [PANDA] Distilled lesson: {lesson_text}")
                memory_manager.save_lesson(session_id, lesson_text)
    except Exception as e:
        print(f"⚠️ [PANDA] Failed to generate post-mortem: {e}")


# ── Action Dispatcher ────────────────────────────────────────────────────────

def _dispatch_action(action_type: str, params: dict, session_id: str) -> str:
    """
    Dispatches a single action to the appropriate handler in action_tools.
    Returns the result string from the handler.
    """
    handler_name = f"handle_{action_type}"
    handler = getattr(action_tools, handler_name, None)
    
    if not handler:
        return f"Error: Unknown action '{action_type}'"
    
    if not isinstance(params, dict):
        params = {}
    
    # Map parameters to handler arguments
    if action_type == "click":
        return handler(params.get("target", ""), session_id)
    elif action_type == "right_click":
        return handler(params.get("target", ""), session_id)
    elif action_type == "type":
        return handler(params.get("text", ""), session_id)
    elif action_type == "press":
        return handler(params.get("key", ""), session_id)
    elif action_type == "scroll":
        return handler(params.get("direction", ""), session_id)
    elif action_type == "drag":
        return handler(params.get("source", ""), params.get("target", ""), session_id)
    elif action_type == "browser_open":
        return handler(params.get("url", ""), session_id)
    elif action_type == "browser_search":
        return handler(params.get("query", ""), session_id)
    elif action_type == "browser_fill":
        return handler(params.get("selector", ""), params.get("text", ""), session_id)
    elif action_type == "browser_click":
        return handler(params.get("selector", ""), session_id)
    elif action_type == "browser_scroll":
        return handler(params.get("direction", ""), session_id)
    elif action_type == "system_search":
        return handler(params.get("query", ""), session_id)
    elif action_type == "select_and_copy":
        return handler(params.get("target", ""), session_id)
    else:
        return f"Action {action_type} executed."


# ── Milestone OODA Loop ─────────────────────────────────────────────────────

def _execute_milestone(
    milestone: str,
    milestone_index: int,
    total_milestones: int,
    goal: str,
    session_id: str,
    task_state: dict,
    rich_context: str,
    experiences_str: str,
    global_step_counter: dict
) -> str:
    """
    Executes a single milestone using an OODA loop.
    
    The Actor LLM receives ONLY:
      - The active milestone string
      - The current screen state
      - Recent action history for this milestone
    
    Returns:
      - "milestone_complete" if the milestone was achieved
      - "task_fail: <reason>" if the milestone failed permanently
      - "task_aborted" if user aborted
    """
    MAX_RETRIES = MAX_RETRIES_BEFORE_RESET
    
    milestone_history = []  # Actions taken during this milestone
    fail_count = 0          # Consecutive failures
    action_blacklist = []   # Blacklisted (action, target) tuples for retry loop
    step_in_milestone = 0
    
    action_executor.reset_stop()
    
    print(f"\n{'='*60}")
    print(f"📍 MILESTONE {milestone_index + 1}/{total_milestones}: {milestone}")
    print(f"{'='*60}")
    
    while step_in_milestone < MAX_STEPS_PER_MILESTONE:
        # Check global stop event
        if action_executor.STOP_EVENT.is_set():
            print("\n🛑 \033[31mTask Aborted by User (STOP_EVENT).\033[0m")
            return "task_aborted"
        
        global_step_counter["count"] += 1
        step_in_milestone += 1
        total_steps = global_step_counter["count"]
        
        # Global limits
        if total_steps == SOFT_LIMIT:
            print("\n⚠️ \033[33mSoft Limit Reached (20 steps total).\033[0m")
            ans = input("PANDA is taking longer than expected. Continue? [Y/N]: ").strip().lower()
            if ans not in ('y', 'yes'):
                return "task_aborted"
                
        if total_steps >= TOTAL_HARD_LIMIT:
            print("\n❌ \033[31mHard Limit Reached (40 steps total). Forcing abort.\033[0m")
            return "task_fail: Hard step limit reached"
        
        print(f"\n--- Step {total_steps} (Milestone {milestone_index + 1}, Action {step_in_milestone}) ---")
        
        # 0. SAFETY: Check for external mouse movement
        from action.mouse_controller import wait_for_user_idle
        wait_for_user_idle(10.0)
        
        # 1. OBSERVE
        print("👀 \033[36mObserve:\033[0m Capturing screen state...")
        screen = _capture_screen_with_retry(session_id)
        
        # Clean screen observations for 8B context
        unique_texts = []
        seen = set()
        for t in screen.get("visible_text", []):
            txt = t.get("text", "").strip()
            if txt and txt not in seen:
                seen.add(txt)
                unique_texts.append(txt)
                
        simplified_screen = {
            "active_window": screen.get("active_window", "Unknown"),
            "ui_controls": screen.get("ui_controls", []),
            "summary": screen.get("summary", "No details"),
            "visible_texts_on_screen": unique_texts[:40]
        }
        
        # 2. ORIENT / DECIDE — Build the Actor prompt
        system_prompt = get_actor_system_prompt(milestone, milestone_index, total_milestones)
        
        # Build injection addons
        injection_addons = []
        
        # Loop detection
        if len(milestone_history) >= 3:
            last_3 = milestone_history[-3:]
            targets = []
            for item in last_3:
                act = item.get("action")
                params = item.get("parameters") or {}
                tgt = params.get("target") or params.get("selector") or params.get("query") or params.get("text") or params.get("url") or params.get("key") or ""
                targets.append((act, tgt))
            if len(set(targets)) == 1:
                loop_action, loop_target = targets[0]
                injection_addons.append(
                    f"\n⚠️ LOOP DETECTED: You have attempted '{loop_action}' on target '{loop_target}' 3 times in a row. "
                    f"STOP repeating this action! Try a completely different action or strategy."
                )
                print(f"⚠️ [PANDA] Loop detected for action '{loop_action}' on target '{loop_target}'. Injecting override.")
        
        # Action blacklist injection
        if action_blacklist:
            blacklist_str = ", ".join([f"'{a}' on '{t}'" for a, t in action_blacklist])
            injection_addons.append(
                f"\n🚫 BLACKLISTED ACTIONS (recently failed, do NOT repeat): {blacklist_str}"
            )
        
        # Recent milestone history (last 5 actions only)
        recent_history = milestone_history[-5:] if milestone_history else []
        
        user_context = f"""
{rich_context}

OVERALL GOAL: {goal}

RECENT ACTIONS FOR THIS MILESTONE:
{json.dumps(recent_history, indent=2) if recent_history else "No actions taken yet."}

SCREEN OBSERVATION:
{json.dumps(simplified_screen, indent=2)}

{experiences_str}

---
INSTRUCTION:
You are working on milestone: "{milestone}"
Decide the NEXT SINGLE ACTION to take to achieve this milestone.
{"".join(injection_addons)}
You must respond with a FLAT JSON structure. 'action' must be a string, 'parameters' must be a flat dictionary.
Example:
{{
  "think": "Your analysis",
  "action": "click",
  "parameters": {{
    "target": "Save button"
  }}
}}
"""
        
        # 3. DECIDE — Call the Actor LLM
        critic_attempts = 0
        critic_feedback_addon = ""
        decision = None
        
        while critic_attempts < 2:
            current_user_context = user_context
            if critic_feedback_addon:
                current_user_context += critic_feedback_addon
            
            # Write debug payload
            try:
                os.makedirs("scratch", exist_ok=True)
                with open("scratch/llm_payload.json", "w", encoding="utf-8") as f:
                    json.dump({"system_prompt": system_prompt, "user_prompt": current_user_context}, f, indent=2)
            except Exception:
                pass
            
            print("💭 \033[35mThink:\033[0m Consulting Actor LLM...")
            try:
                response = _client.chat(
                    model=MODEL_NAME,
                    format='json',
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': current_user_context}
                    ],
                    options={"temperature": 0.1}
                )
                raw = response['message']['content'].strip()
                
                # Clean possible markdown
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                
                decision = json.loads(raw)
                if not decision or not isinstance(decision, dict):
                    raise ValueError("LLM returned an empty or invalid JSON structure.")
                
                # Extract action (flat format only)
                action_val = decision.get("action")
                if not action_val:
                    raise ValueError("LLM response is missing 'action' key.")
                
                # Normalize: if action is a dict (nested format), extract it
                if isinstance(action_val, dict):
                    action_type = action_val.get("type") or action_val.get("action")
                    params = action_val.get("parameters", decision.get("parameters", {}))
                else:
                    action_type = str(action_val)
                    params = decision.get("parameters", {})
                
                if not isinstance(params, dict):
                    params = {}
                
                decision["_action_type"] = action_type
                decision["_params"] = params
                
                # --- CRITIC CHECK ---
                from action.action_critic import critique_action
                print("🧐 \033[36mCritic:\033[0m Checking proposed action...")
                critique = critique_action(goal, screen.get("summary", "No details"), decision)
                
                if critique.get("approved", True):
                    print(f"🧐 \033[32mCritic Approved:\033[0m {critique.get('feedback', 'No feedback')}")
                    break
                else:
                    print(f"🧐 \033[31mCritic Rejected:\033[0m {critique.get('feedback', 'No feedback')}")
                    critic_attempts += 1
                    critic_feedback_addon = f"\n\n⚠️ CRITIC REJECTION (Attempt {critic_attempts}/2):\nFeedback: {critique.get('feedback')}\nPlease adjust and propose a DIFFERENT, VALID action."
                    if critic_attempts >= 2:
                        print("⚠️ [PANDA] Max critic rejections reached. Proceeding with last decision anyway.")
                        break
                        
            except Exception as e:
                print(f"❌ \033[31mLLM Error:\033[0m {e}")
                fail_count += 1
                if fail_count >= MAX_RETRIES:
                    return "task_fail: LLM errors exceeded retry limit"
                time.sleep(1)
                continue
        
        if not decision:
            continue
        
        action_type = decision.get("_action_type", "")
        params = decision.get("_params", {})
        think_text = decision.get("think", "No thoughts provided.")
        
        print(f"💭 \033[35mThought:\033[0m {think_text}")
        
        # 4. ACT
        
        # Handle milestone completion signal
        if action_type in ("milestone_complete", "complete"):
            print(f"✅ \033[32mMilestone Complete!\033[0m {milestone}")
            task_state["completed_milestones"].append(milestone)
            return "milestone_complete"
        
        # Handle fail signal
        if action_type == "fail":
            reason = params.get("reason", "Unknown reason")
            print(f"❌ \033[31mPANDA gave up:\033[0m {reason}")
            return f"task_fail: {reason}"
        
        # HITL Destructive Action Gatekeeping
        if action_executor.is_destructive(action_type, params):
            print(f"\n⚠️ \033[41;97m DESTRUCTIVE ACTION DETECTED \033[0m")
            print(f"Action: {action_type} | Params: {params}")
            ans = input("Proceed? [Y/N]: ").strip().lower()
            if ans not in ('y', 'yes'):
                print("🛑 Action blocked by user.")
                return "task_aborted"
            print("✅ User approved destructive action — this is now a commit point.")
        
        # Execute the action
        print(f"🖱 \033[33mAct:\033[0m {action_type}({params})")
        
        try:
            result_str = _dispatch_action(action_type, params, session_id)
            
            # 5. VERIFY
            print(f"✅ \033[32mVerify:\033[0m {result_str}")
            
            # Record in milestone history
            milestone_history.append({
                "step": step_in_milestone,
                "action": action_type,
                "parameters": params,
                "result": result_str
            })
            
            # Also record in global task history
            task_state["history"].append({
                "step": global_step_counter["count"],
                "milestone": milestone,
                "action": action_type,
                "parameters": params,
                "result": result_str
            })
            
            # Check if the action failed
            if "couldn't" in result_str or "error" in result_str.lower():
                fail_count += 1
                
                # Add to blacklist for re-routing
                target_key = params.get("target") or params.get("selector") or params.get("query") or params.get("text") or ""
                if target_key:
                    action_blacklist.append((action_type, target_key))
                
                if fail_count >= MAX_RETRIES:
                    print(f"\n⚠️ \033[33m{MAX_RETRIES} consecutive failures on this milestone.\033[0m")
                    return "milestone_stuck"
                    
                print(f"⚠️ [PANDA] Action failed ({fail_count}/{MAX_RETRIES}). Re-routing...")
            else:
                fail_count = 0          # Reset on success
                action_blacklist = []   # Clear blacklist on success
                
        except Exception as e:
            print(f"❌ \033[31mExecution Error:\033[0m {e}")
            fail_count += 1
            milestone_history.append({
                "step": step_in_milestone,
                "action": action_type,
                "parameters": params,
                "result": f"Exception: {e}"
            })
            if fail_count >= MAX_RETRIES:
                return "milestone_stuck"
        
        time.sleep(1.0)
    
    # Exceeded MAX_STEPS_PER_MILESTONE
    print(f"\n⚠️ \033[33mMax steps per milestone reached ({MAX_STEPS_PER_MILESTONE}).\033[0m")
    return "milestone_stuck"


# ── Main Entry Point ─────────────────────────────────────────────────────────

def execute_autonomous_task(task_description: str, session_id: str = "auto_task", milestones: list = None) -> str:
    """
    Main entry point for task execution.
    
    Manages the milestone queue, executes each milestone via _execute_milestone(),
    and handles Home Base Resets when milestones get stuck.
    
    Args:
        task_description: The user's goal description
        session_id: Session identifier for logging
        milestones: List of milestone strings from the Decomposer
    """
    from vector_memory import semantic_search_trajectories, save_trajectory_semantic
    
    print(f"\n🚀 \033[1;35mStarting Autonomous Task:\033[0m {task_description}")
    
    if not milestones:
        milestones = []
    
    # Build rich context
    print("🔍 [PANDA] Building task context from system state and memory...")
    rich_context = ""
    try:
        rich_context = build_rich_task_context(task_description, session_id)
    except Exception as e:
        print(f"⚠️ [PANDA] Failed to build rich task context: {e}")
        
    # Search past experiences
    print("🔍 [PANDA] Searching past experiences for similar tasks...")
    past_experiences = []
    try:
        past_experiences = semantic_search_trajectories(task_description, top_k=2)
    except Exception as e:
        print(f"⚠️ [PANDA] Failed to load past experiences: {e}")
        
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
    
    # Initialize task state
    task_state = {
        "goal": task_description,
        "milestones": milestones,
        "completed_milestones": [],
        "history": [],
    }
    
    global_step_counter = {"count": 0}
    status = "failed"
    outcome_summary = "Task execution failed or aborted."
    
    try:
        # ── MILESTONE QUEUE PROCESSING ────────────────────────────────────
        
        if not milestones:
            print("⚠️ [PANDA] No milestones generated. Running in single-shot mode.")
            # Fallback: treat the entire task as a single milestone
            milestones = [task_description]
            task_state["milestones"] = milestones
        
        total = len(milestones)
        print(f"\n📋 \033[1;34mExecution Plan ({total} milestones):\033[0m")
        for i, ms in enumerate(milestones):
            print(f"  {i+1}. {ms}")
        print()
        
        milestone_idx = 0
        
        while milestone_idx < total:
            current_milestone = milestones[milestone_idx]
            reset_count = 0
            
            while reset_count <= MAX_MILESTONE_RESETS:
                result = _execute_milestone(
                    milestone=current_milestone,
                    milestone_index=milestone_idx,
                    total_milestones=total,
                    goal=task_description,
                    session_id=session_id,
                    task_state=task_state,
                    rich_context=rich_context,
                    experiences_str=experiences_str,
                    global_step_counter=global_step_counter
                )
                
                if result == "milestone_complete":
                    print(f"✅ Milestone {milestone_idx + 1}/{total} complete: {current_milestone}")
                    milestone_idx += 1
                    break
                    
                elif result == "task_aborted":
                    outcome_summary = "Task was aborted by user."
                    return outcome_summary
                    
                elif result.startswith("task_fail:"):
                    reason = result.replace("task_fail:", "").strip()
                    outcome_summary = f"Failed: {reason}"
                    return outcome_summary
                    
                elif result == "milestone_stuck":
                    reset_count += 1
                    if reset_count > MAX_MILESTONE_RESETS:
                        print(f"\n❌ \033[31mMilestone '{current_milestone}' failed after {MAX_MILESTONE_RESETS} Home Base Resets.\033[0m")
                        outcome_summary = f"Failed: Stuck on milestone '{current_milestone}' after {MAX_MILESTONE_RESETS} resets."
                        return outcome_summary
                    
                    # ── HOME BASE RESET ──────────────────────────────────
                    print(f"\n🏠 \033[41;97m HOME BASE RESET {reset_count}/{MAX_MILESTONE_RESETS} \033[0m")
                    print(f"   Milestone '{current_milestone}' is stuck. Killing active app and restarting...")
                    
                    try:
                        kill_result = action_executor.kill_active_app()
                        print(f"   🔄 {kill_result.get('details', 'App killed.')}")
                    except Exception as kill_err:
                        print(f"   ⚠️ Kill failed: {kill_err}")
                    
                    time.sleep(3.0)  # Wait for app to fully close
                    print(f"   🔄 Restarting milestone from clean slate...")
                    continue
                    
                else:
                    # Unknown result — treat as failure
                    outcome_summary = f"Failed: Unknown result '{result}'"
                    return outcome_summary
        
        # All milestones complete
        outcome_summary = f"Successfully completed: {task_description}"
        status = "success"
        print(f"\n🎉 \033[1;32mAll {total} milestones completed successfully!\033[0m")
        
        return outcome_summary
        
    finally:
        # Prompt user for feedback
        print(f"\n📊 [PANDA] Outcome: {outcome_summary}")
        print("\n💬 \033[1;36mHow did I do? Anything I should do differently next time?\033[0m")
        try:
            feedback = input("Feedback: ").strip()
            if feedback:
                _extract_and_save_user_preference(feedback, session_id)
        except (EOFError, Exception):
            pass
        
        # Post-Mortem if failures occurred
        has_errors = False
        if task_state.get("history"):
            for h in task_state["history"]:
                res = str(h.get("result", "")).lower()
                if "couldn't" in res or "error" in res:
                    has_errors = True
                    break
        
        if status == "failed" or has_errors:
            try:
                _generate_post_mortem(task_description, task_state.get("history", []), session_id)
            except Exception as pm_err:
                print(f"⚠️ [PANDA] Error during post-mortem distillation: {pm_err}")

        if task_state["history"]:
            try:
                steps_json = json.dumps(task_state["history"])
                save_trajectory_semantic(
                    goal=task_description,
                    steps_json=steps_json,
                    status=status,
                    summary=outcome_summary
                )
                print(f"💾 [PANDA] Experience saved to database with status: '{status}'")
            except Exception as db_err:
                print(f"⚠️ [PANDA] Error saving trajectory to database: {db_err}")
