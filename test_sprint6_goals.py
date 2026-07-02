"""
Test Suite for Sprint 6: Goal Engine & Autonomous Planning
=========================================================
Validates database storage, Ollama plan decomposition, version replanning,
step dependencies, progress tracking, prioritisation logic, velocity metrics,
nudge reflections on session exit, and proactive system prompt injection.
"""

import os
import sys
import json
import datetime
from unittest.mock import MagicMock

# Ensure we can import from the project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_manager
import vector_memory
import goal_engine
import reflection_engine
import smart_brain

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []


def test(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append(condition)
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")
    if not condition:
        print(f"         \033[31m^ FAILED\033[0m")


def cleanup_test_db():
    for filename in ["panda_memory_test.db", "panda_memory_test.db-wal", "panda_memory_test.db-shm"]:
        path = os.path.join(memory_manager.MEMORY_DIR, filename)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


print("\n" + "=" * 60)
print("  PANDA Sprint 6 Goal Engine Test Suite")
print("=" * 60)

# Setup Test Database
print("\n  [Setup] Initializing isolated test database...")
cleanup_test_db()
TEST_DB_PATH = os.path.join(memory_manager.MEMORY_DIR, "panda_memory_test.db")
memory_manager.DB_PATH = TEST_DB_PATH

memory_manager.initialize_memory()
session_id = "test_sprint6_session"

# Mock Ollama Client
mock_client = MagicMock()
goal_engine._get_ollama_client = lambda: mock_client

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1: Database Schema Check
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 1: Database Schema Check ---")
conn = memory_manager._get_connection()
cursor = conn.cursor()

# Check tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = {row["name"] for row in cursor.fetchall()}

# Check columns on goals table
cursor.execute("PRAGMA table_info(goals)")
cols_goals = {row["name"] for row in cursor.fetchall()}

# Check columns on goal_steps
cursor.execute("PRAGMA table_info(goal_steps)")
cols_steps = {row["name"] for row in cursor.fetchall()}

# Check columns on goal_plans
cursor.execute("PRAGMA table_info(goal_plans)")
cols_plans = {row["name"] for row in cursor.fetchall()}

conn.close()

test("goal_steps table exists", "goal_steps" in tables)
test("goal_plans table exists", "goal_plans" in tables)
test("goals has priority column", "priority" in cols_goals)
test("goals has manual_priority_weight column", "manual_priority_weight" in cols_goals)
test("goals has completion_velocity column", "completion_velocity" in cols_goals)
test("goals has target_date column", "target_date" in cols_goals)
test("goals has progress_pct column", "progress_pct" in cols_goals)
test("goals has current_plan_version column", "current_plan_version" in cols_goals)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: Save and Load Steps
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 2: Save and Load Steps ---")
# Insert a test goal
goal_id = memory_manager.save_goal(session_id, "Become Exchange Admin")

# Save 2 steps
step1_id = memory_manager.save_goal_step(goal_id, plan_version=1, step_number=1, step_text="Learn Exchange Online")
step2_id = memory_manager.save_goal_step(goal_id, plan_version=1, step_number=2, step_text="Learn Azure Active Directory", depends_on=step1_id)

steps = memory_manager.load_goal_steps(goal_id, plan_version=1)
test("Correct number of steps loaded", len(steps) == 2)
if len(steps) == 2:
    test("Steps sorted by step_number", steps[0]["step_number"] == 1 and steps[1]["step_number"] == 2)
    test("Dependency mapping correctly stored", steps[1]["depends_on"] == step1_id)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: Decompose Goal (v1 Plan)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 3: Decompose Goal (v1 Plan) ---")
# Mock Ollama plan return
mock_client.chat.return_value = {
    "message": {
        "content": json.dumps([
            {"step": 1, "text": "Set up environment", "depends_on": None},
            {"step": 2, "text": "Install dependencies", "depends_on": 1},
            {"step": 3, "text": "Write code logic", "depends_on": 2}
        ])
    }
}

goal_id_2 = memory_manager.save_goal(session_id, "Build Python Voice Assistant")
v1_steps = goal_engine.decompose_goal(goal_id_2, "Build Python Voice Assistant", plan_version=1)

test("Decompose returned steps list", len(v1_steps) == 3)
if len(v1_steps) == 3:
    test("Step dependencies linked correctly", v1_steps[1]["depends_on"] == v1_steps[0]["id"])
    test("Plan version matches 1", v1_steps[0]["plan_version"] == 1)

# Check plan meta saved
meta = memory_manager.load_goal_plan_meta(goal_id_2, version=1)
test("Goal plan metadata successfully stored", meta is not None and meta["plan_version"] == 1)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: Replanning / Version History
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 4: Replanning / Version History ---")
# Mock Ollama new plan
mock_client.chat.return_value = {
    "message": {
        "content": json.dumps([
            {"step": 1, "text": "Set up Python Environment", "depends_on": None},
            {"step": 2, "text": "Research voice engines", "depends_on": None},
            {"step": 3, "text": "Develop voice logic", "depends_on": 2},
            {"step": 4, "text": "Conduct final verification", "depends_on": 3}
        ])
    }
}

# Re-plan goal_id_2 as plan version 2
v2_steps = goal_engine.decompose_goal(goal_id_2, "Build Python Voice Assistant", plan_version=2)

test("Replanned v2 steps length matches", len(v2_steps) == 4)
history = memory_manager.load_goal_plan_history(goal_id_2)
test("Two plan versions exist in history", len(history) == 2)
if len(history) == 2:
    test("History ordered descending by version", history[0]["plan_version"] == 2 and history[1]["plan_version"] == 1)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5: Step Dependencies & Suggesting Next Action
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 5: Step Dependencies & Suggesting Next Action ---")
# Reset step status for goal_id
steps_id_1 = memory_manager.load_goal_steps(goal_id)
# Verify step 2 depends on step 1 (both pending)
next_action = goal_engine.suggest_next_action(goal_id)
test("Next action is Step 1 (first unblocked)", next_action is not None and next_action["step_number"] == 1)

# Mark step 1 completed
memory_manager.update_step_status(steps_id_1[0]["id"], "done")
next_action_after = goal_engine.suggest_next_action(goal_id)
test("Next action is now Step 2 (unblocked)", next_action_after is not None and next_action_after["step_number"] == 2)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 6: Progress Percent updates
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 6: Progress Percent updates ---")
memory_manager.update_goal_progress(goal_id)
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("SELECT progress_pct, current_plan_version FROM goals WHERE id = ?", (goal_id,))
row = dict(cursor.fetchone())
conn.close()

test("Goal progress matches 50% (1/2 steps done)", row["progress_pct"] == 0.5)
test("Current plan version matches active plan", row["current_plan_version"] == 1)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 7: Manual Priority Weight Boosting
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 7: Manual Priority Weight Boosting ---")
# Reset mention counts
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("UPDATE goals SET mention_count = 1, importance_score = 0.5, manual_priority_weight = 0.0 WHERE id = ?", (goal_id,))
cursor.execute("UPDATE goals SET mention_count = 1, importance_score = 0.5, manual_priority_weight = 0.0 WHERE id = ?", (goal_id_2,))
conn.commit()
conn.close()

# Boost goal_id manual priority to rank #1
# priority=1 gives manual_weight=1.0. goal_id_2 gets priority=5 (default) -> manual_weight=0.0
memory_manager.update_goal_priority(goal_id, priority=1, manual_weight=1.0)

# Prioritize
goals = memory_manager.load_goals(status='active')
prioritized = goal_engine.prioritize_goals(goals)

test("Priority boost forces goal to rank #1", prioritized[0]["id"] == goal_id)
test("Goal rank priority field updated in DB", prioritized[0]["priority"] == 1 and prioritized[1]["priority"] == 2)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 8: Completion Velocity
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 8: Completion Velocity ---")
# Set a done step completed 5 days ago (within 30 days)
now_iso = datetime.datetime.now().isoformat()
conn = memory_manager._get_connection()
cursor = conn.cursor()
# Mark step 2 as done too
cursor.execute("UPDATE goal_steps SET status = 'done', updated_at = ? WHERE goal_id = ? AND step_number = 2", (now_iso, goal_id))
conn.commit()
conn.close()

velocity = goal_engine.update_completion_velocity(goal_id)
# 2 steps completed / 4 weeks = 0.5 steps/week
test("Completion velocity calculated correctly", velocity == 0.5)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 9: Goal Abandonment (Soft Archiving)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 9: Goal Abandonment (Soft Archiving) ---")
# Abandon goal_id_2
memory_manager.update_goal_status(goal_id_2, "abandoned")

active_goals = memory_manager.load_goals(status='active')
active_ids = {g["id"] for g in active_goals}
test("Abandoned goal excluded from active lists", goal_id_2 not in active_ids)

# Check vector loading filters out abandoned
all_mems = memory_manager.load_all_memories_with_embeddings()
all_goal_ids = {m["source_id"] for m in all_mems if m["source_table"] == "goals"}
test("Abandoned goal excluded from active vector space", goal_id_2 not in all_goal_ids)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 10: Proactive Prompt Injection
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 10: Proactive Prompt Injection ---")
# Goal 1 has all steps done. Let's reset step 2 to pending so it is active
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("UPDATE goal_steps SET status = 'pending' WHERE goal_id = ? AND step_number = 2", (goal_id,))
conn.commit()
conn.close()
memory_manager.update_goal_progress(goal_id)

top_goal_info = goal_engine.get_highest_priority_goal_with_next_step()
test("Helper retrieves top priority goal details", top_goal_info is not None)
if top_goal_info:
    test("Helper returns correct next step text", top_goal_info["goal_text"] == "Become Exchange Admin" and "Active Directory" in top_goal_info["next_step"])


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 11: Reflection on Exit (Stale Reminders & Velocity)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 11: Reflection on Exit (Stale Reminders & Velocity) ---")
# Make updated_at of goal_id 15 days ago to trigger stale nudge
fifteen_days_ago = (datetime.datetime.now() - datetime.timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("UPDATE goals SET updated_at = ? WHERE id = ?", (fifteen_days_ago, goal_id))
conn.commit()
conn.close()

# Run goals reflection processing
reflection_engine.process_goals_reflection()

reflections = memory_manager.load_reflections(reflection_type="nudge")
test("Saved stale nudge reflection for inactive goal", len(reflections) >= 1)
if len(reflections) >= 1:
    test("Nudge contains correct warning text", "no progress in 15 days" in reflections[0]["insight_text"])


# Teardown Test Database
print("\n[Teardown] Cleaning up test database...")
cleanup_test_db()

# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
passed = sum(results)
total = len(results)
if passed == total:
    print(f"   ALL {total} TESTS PASSED ")
else:
    print(f"   {passed}/{total} TESTS PASSED ({total - passed} FAILED) ")
print("=" * 60 + "\n")
sys.exit(0 if passed == total else 1)
