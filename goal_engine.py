"""
✨ PANDA — Goal Engine & Autonomous Planning (Sprint 6)
======================================================
Coordinates planning, sub-step decomposition, prioritization, and dependency tracking.
"""

import os
import json
import sqlite3
import datetime
import ollama

import memory_manager
import vector_memory

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")


def _get_ollama_client() -> ollama.Client:
    return ollama.Client(host=OLLAMA_URL, timeout=120.0, headers={"ngrok-skip-browser-warning": "true"})


def decompose_goal(goal_id: int, goal_text: str, plan_version: int) -> list:
    """
    Decomposes a goal into a list of 3-8 structured steps using Ollama.
    Saves steps to the goal_steps table and metadata to goal_plans.
    """
    print(f"  [GoalEngine] Decomposing goal {goal_id} (v{plan_version}): '{goal_text}'...")
    
    prompt = (
        "You are PANDA's planning assistant.\n"
        f"Break this goal into 3 to 8 concrete, ordered steps:\n"
        f"Goal: \"{goal_text}\"\n\n"
        "Output format: Return ONLY a valid JSON array of objects. Example:\n"
        "[\n"
        "  {{\"step\": 1, \"text\": \"Step description\", \"depends_on\": null}}\n"
        "]\n"
        "Rules:\n"
        "- 'step' is a 1-indexed sequential integer.\n"
        "- 'depends_on' is the 'step' number this step depends on (or null).\n"
        "Reply with ONLY raw JSON. No markdown backticks, no explanations."
    )
    
    try:
        client = _get_ollama_client()
        response = client.chat(
            model=MODEL_NAME,
            format="json",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 1024}
        )
        
        raw = response["message"]["content"].strip()
        steps_data = json.loads(raw)
        
        if not isinstance(steps_data, list):
            # Try to see if it's wrapped in an object
            if isinstance(steps_data, dict) and "steps" in steps_data:
                steps_data = steps_data["steps"]
            else:
                raise ValueError("LLM response is not a list")

        # Map step number (from JSON) -> DB auto-increment ID
        step_to_db_id = {}
        
        # Save to goal_steps
        inserted_steps = []
        for item in steps_data:
            step_num = item.get("step")
            step_text = item.get("text", "").strip()
            depends_on_step_num = item.get("depends_on")
            
            if not step_text or step_num is None:
                continue
                
            # Resolve depends_on
            dep_db_id = None
            if depends_on_step_num is not None:
                dep_db_id = step_to_db_id.get(depends_on_step_num)
                
            db_id = memory_manager.save_goal_step(
                goal_id=goal_id,
                plan_version=plan_version,
                step_number=step_num,
                step_text=step_text,
                depends_on=dep_db_id
            )
            step_to_db_id[step_num] = db_id
            inserted_steps.append({
                "id": db_id,
                "goal_id": goal_id,
                "plan_version": plan_version,
                "step_number": step_num,
                "step_text": step_text,
                "status": "pending",
                "depends_on": dep_db_id
            })
            
        # Save goal plan metadata
        memory_manager.save_goal_plan_meta(
            goal_id=goal_id,
            version=plan_version,
            model=MODEL_NAME,
            raw_json=raw
        )
        
        # Update progress and current version caches on the goal
        memory_manager.update_goal_progress(goal_id)
        
        print(f"  [GoalEngine] Generated and saved plan v{plan_version} with {len(inserted_steps)} steps.")
        return inserted_steps
        
    except Exception as e:
        print(f"  [GoalEngine] Error planning goal {goal_id}: {e}")
        # Fallback basic step plan if LLM fails
        fallback_steps = [
            {"step": 1, "text": "Define core scope and requirements", "depends_on": None},
            {"step": 2, "text": "Research tools, techniques, and resources", "depends_on": 1},
            {"step": 3, "text": "Execute first phase milestones", "depends_on": 2},
            {"step": 4, "text": "Verify, test, and finalize results", "depends_on": 3}
        ]
        step_to_db_id = {}
        inserted_steps = []
        for fallback in fallback_steps:
            dep_db_id = step_to_db_id.get(fallback["depends_on"])
            db_id = memory_manager.save_goal_step(
                goal_id=goal_id,
                plan_version=plan_version,
                step_number=fallback["step"],
                step_text=fallback["text"],
                depends_on=dep_db_id
            )
            step_to_db_id[fallback["step"]] = db_id
            inserted_steps.append({
                "id": db_id,
                "goal_id": goal_id,
                "plan_version": plan_version,
                "step_number": fallback["step"],
                "step_text": fallback["text"],
                "status": "pending",
                "depends_on": dep_db_id
            })
            
        memory_manager.save_goal_plan_meta(
            goal_id=goal_id,
            version=plan_version,
            model="fallback",
            raw_json=json.dumps(fallback_steps)
        )
        memory_manager.update_goal_progress(goal_id)
        return inserted_steps


def _days_since_update(goal: dict) -> float:
    updated_at_str = goal.get("updated_at")
    if not updated_at_str:
        return 0.0
    try:
        updated_at = datetime.datetime.fromisoformat(updated_at_str)
        delta = datetime.datetime.now() - updated_at
        return max(0.0, delta.days + delta.seconds / 86400.0)
    except Exception:
        return 0.0


def _deadline_urgency(target_date_str: str) -> float:
    if not target_date_str:
        return 0.0
    try:
        target_date = datetime.datetime.fromisoformat(target_date_str)
        delta = target_date - datetime.datetime.now()
        days_left = delta.days + delta.seconds / 86400.0
        if days_left <= 0:
            return 10.0  # Overdue goals get max urgency boost
        elif days_left <= 7:
            return 8.0   # Under a week
        elif days_left <= 30:
            return 4.0   # Under a month
        else:
            return 1.0   # More than a month
    except Exception:
        return 0.0


def _compute_priority_score(goal: dict) -> float:
    mention_score = goal.get("mention_count", 1) * 1.5
    importance_score = goal.get("importance_score", 0.5) * 8.0
    manual_boost = goal.get("manual_priority_weight", 0.0) * 15.0
    velocity_boost = goal.get("completion_velocity", 0.0) * 5.0
    age_penalty = _days_since_update(goal) * 0.15
    deadline_boost = _deadline_urgency(goal.get("target_date"))
    
    score = mention_score + importance_score + manual_boost + velocity_boost + deadline_boost - age_penalty
    
    if goal.get("status") == "paused":
        # Paused goals get priority halved
        return score * 0.5
        
    return score


def prioritize_goals(goals: list) -> list:
    """Calculates priority scores for a list of goals, updates goals table priority field, and returns sorted list."""
    scored_goals = []
    for goal in goals:
        score = _compute_priority_score(goal)
        goal["priority_score"] = score
        scored_goals.append(goal)
        
    # Sort descending by priority score
    scored_goals.sort(key=lambda x: x["priority_score"], reverse=True)
    
    # Map back to rank (1 = highest score, 2, 3...)
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    for rank, goal in enumerate(scored_goals, 1):
        cursor.execute("""
            UPDATE goals 
            SET priority = ?
            WHERE id = ?
        """, (rank, goal["id"]))
        goal["priority"] = rank
    conn.commit()
    conn.close()
    
    return scored_goals


def suggest_next_action(goal_id: int) -> dict | None:
    """Suggests the next action step to take for a goal, considering dependencies."""
    return memory_manager.get_next_action(goal_id)


def detect_blockers(goal_id: int) -> list:
    """Returns a list of steps that are blocked because their dependency steps are not done."""
    steps = memory_manager.load_goal_steps(goal_id)
    if not steps:
        return []
    
    step_status = {s["id"]: s["status"] for s in steps}
    blocked_steps = []
    
    for step in steps:
        if step["status"] in ('pending', 'in_progress'):
            dep = step["depends_on"]
            if dep is not None:
                dep_status = step_status.get(dep)
                if dep_status != 'done':
                    blocked_steps.append(step)
    return blocked_steps


def generate_progress_report(goal_id: int) -> str:
    """Generates a formatted text checklist of step progress for a goal."""
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
    goal = cursor.fetchone()
    conn.close()
    if not goal:
        return "❌ Goal not found."
    
    goal = dict(goal)
    steps = memory_manager.load_goal_steps(goal_id)
    
    ver = goal.get("current_plan_version", 1)
    status_label = goal.get("status", "active")
    progress_pct = goal.get("progress_pct", 0.0)
    velocity = goal.get("completion_velocity", 0.0)
    
    total = len(steps)
    done = sum(1 for s in steps if s["status"] == 'done')
    
    # Progress bar
    bar_width = 15
    filled_width = int(progress_pct * bar_width)
    progress_bar = "█" * filled_width + "░" * (bar_width - filled_width)
    
    report_lines = []
    report_lines.append(f"🎯 {goal['goal_text']}     [v{ver} plan — {status_label}]")
    report_lines.append(f"   Progress: {done} / {total} steps  ({progress_pct:.0%})  {progress_bar}")
    report_lines.append(f"   Velocity: {velocity:.2f} steps/week")
    report_lines.append("")
    
    for idx, s in enumerate(steps, 1):
        status_icon = "⏳"
        status_tag = ""
        
        if s["status"] == 'done':
            status_icon = "✅"
        elif s["status"] == 'in_progress':
            status_icon = "🔄"
            status_tag = "  ← CURRENT"
        elif s["status"] == 'blocked':
            status_icon = "❌"
            status_tag = "  (blocked)"
        else: # pending
            dep = s["depends_on"]
            if dep is not None:
                dep_step = next((x for x in steps if x["id"] == dep), None)
                if dep_step and dep_step["status"] != 'done':
                    status_icon = "⏳"
                    status_tag = f"  (blocked until step {dep_step['step_number']} done)"
                    
        notes = f" - Note: {s['notes']}" if s.get('notes') else ""
        report_lines.append(f"   {status_icon}  {idx}. {s['step_text']}{status_tag}{notes}")
        
    return "\n".join(report_lines)


def update_completion_velocity(goal_id: int) -> float:
    """Computes steps completed per week over the trailing 30 days, and updates goals table."""
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT current_plan_version FROM goals WHERE id = ?", (goal_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return 0.0
    
    current_ver = row["current_plan_version"]
    if not current_ver or current_ver == 0:
        conn.close()
        return 0.0
        
    cursor.execute("""
        SELECT updated_at FROM goal_steps 
        WHERE goal_id = ? AND plan_version = ? AND status = 'done'
    """, (goal_id, current_ver))
    rows = cursor.fetchall()
    conn.close()
    
    done_count = 0
    now = datetime.datetime.now()
    for r in rows:
        try:
            completed_time = datetime.datetime.fromisoformat(r["updated_at"])
            if (now - completed_time).days <= 30:
                done_count += 1
        except Exception:
            done_count += 1
            
    velocity = done_count / 4.0 # 30 days is approx 4 weeks
    
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE goals 
        SET completion_velocity = ?
        WHERE id = ?
    """, (velocity, goal_id))
    conn.commit()
    conn.close()
    return velocity


def get_highest_priority_goal_with_next_step() -> dict | None:
    """Loads active goals, prioritizes them, and returns the top goal with its next action step."""
    goals = memory_manager.load_goals(status='active')
    if not goals:
        return None
        
    prioritized = prioritize_goals(goals)
    planned_goals = [g for g in prioritized if g.get("current_plan_version", 0) > 0]
    if not planned_goals:
        return None
        
    top_goal = planned_goals[0]
    next_step = suggest_next_action(top_goal["id"])
    
    if next_step:
        return {
            "goal_text": top_goal["goal_text"],
            "next_step": next_step["step_text"],
            "progress_pct": top_goal.get("progress_pct", 0.0),
            "plan_version": top_goal.get("current_plan_version", 1),
            "priority": top_goal.get("priority", 1)
        }
    return None
