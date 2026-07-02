"""
Test Suite for Sprint 2: Structured Entities (Goals & Projects)
==============================================================
Validates schemas, explicit saving, embedding indexing, automatic mention count checks,
and weighted priority retrieval matching.
"""

import os
import sys
import time

# Ensure we can import from the project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_manager
import vector_memory

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


print("\n" + "=" * 60)
print("  PANDA Sprint 2 Entities Test Suite")
print("=" * 60)

# Setup
print("\n  [Setup] Initializing database...")
memory_manager.initialize_memory()
session_id = "test_sprint2_session"

# Clear old test data if any
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM interactions WHERE session_id = ?", (session_id,))
cursor.execute("DELETE FROM goals WHERE session_id = ?", (session_id,))
cursor.execute("DELETE FROM projects WHERE session_id = ?", (session_id,))
# Only delete vector_memory rows linked to test session interactions/goals/projects
cursor.execute("""
    DELETE FROM vector_memory WHERE
        (source_table = 'interactions' AND source_id IN (SELECT id FROM interactions WHERE session_id = ?))
        OR (source_table = 'goals' AND source_id IN (SELECT id FROM goals WHERE session_id = ?))
        OR (source_table = 'projects' AND source_id IN (SELECT id FROM projects WHERE session_id = ?))
""", (session_id, session_id, session_id))
# Also clean any orphaned test rows by content
cursor.execute("""
    DELETE FROM vector_memory WHERE content_text IN (
        'Become CEO', 'Project Alya: Python voice assistant',
        'I really hope I can be a CEO one day'
    )
""")
conn.commit()
conn.close()

# TEST 1: Database Schema Check
print("\n--- TEST 1: Database Schema Check ---")
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(goals)")
cols_goals = {row["name"] for row in cursor.fetchall()}
cursor.execute("PRAGMA table_info(projects)")
cols_projects = {row["name"] for row in cursor.fetchall()}
conn.close()

expected_goals = {"id", "session_id", "goal_text", "status", "importance_score", 
                  "extracted_from_interaction_id", "confidence", "mention_count", 
                  "created_at", "updated_at"}
expected_projects = {"id", "session_id", "project_name", "description", "importance_score", 
                     "extracted_from_interaction_id", "confidence", "mention_count", 
                     "created_at", "updated_at"}

test("goals table has correct columns", expected_goals.issubset(cols_goals), f"Columns: {cols_goals}")
test("projects table has correct columns", expected_projects.issubset(cols_projects), f"Columns: {cols_projects}")


# TEST 2: Explicit Entity Saving & Source Tracking
print("\n--- TEST 2: Explicit Goal & Project Saving ---")
# 1. Save dummy interaction to act as the source
dummy_int_id = memory_manager.save_interaction(
    session_id=session_id,
    user_message="I want to make a new goal",
    assistant_response="Sure! What is it?",
    importance_score=0.3
)

# 2. Save goal linked to that interaction
goal_id = vector_memory.save_goal_semantic(
    session_id=session_id,
    goal_text="Become CEO",
    status="active",
    extracted_from=dummy_int_id,
    confidence=1.0
)

# 3. Save project linked to that interaction
proj_id = vector_memory.save_project_semantic(
    session_id=session_id,
    project_name="Alya",
    description="Python voice assistant",
    extracted_from=dummy_int_id,
    confidence=0.9
)

# Load and verify
goals = memory_manager.load_goals()
projs = memory_manager.load_projects()

test("Goal saved and retrieved correctly", len(goals) > 0 and goals[0]["goal_text"] == "Become CEO")
if goals:
    test("Goal source tracked correctly", goals[0]["extracted_from_interaction_id"] == dummy_int_id)
    test("Goal confidence matches input", goals[0]["confidence"] == 1.0)
    test("Goal mention count initialized to 1", goals[0]["mention_count"] == 1)

test("Project saved and retrieved correctly", len(projs) > 0 and projs[0]["project_name"] == "Alya")
if projs:
    test("Project source tracked correctly", projs[0]["extracted_from_interaction_id"] == dummy_int_id)
    test("Project confidence matches input", projs[0]["confidence"] == 0.9)
    test("Project mention count initialized to 1", projs[0]["mention_count"] == 1)


# TEST 3: Indexing in Vector Memory
print("\n--- TEST 3: Semantic Indexing ---")
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("SELECT source_table, source_id, content_text FROM vector_memory WHERE source_table IN ('goals', 'projects')")
indexed_rows = cursor.fetchall()
conn.close()

goals_indexed = any(row["source_table"] == "goals" and row["source_id"] == goal_id for row in indexed_rows)
projs_indexed = any(row["source_table"] == "projects" and row["source_id"] == proj_id for row in indexed_rows)

test("Goal indexed in vector memory", goals_indexed)
test("Project indexed in vector memory", projs_indexed)


# TEST 4: Dynamic Mention Count Updates
print("\n--- TEST 4: Dynamic Mention Count Updates ---")
# Call save_turn_semantic with a message highly similar to "Become CEO"
vector_memory.save_turn_semantic(session_id, "I really hope I can be a CEO one day", "You will succeed!")

# Wait a brief moment for background check to complete
time.sleep(0.5)

updated_goals = memory_manager.load_goals()
test("Goal mention count incremented dynamically", updated_goals[0]["mention_count"] == 2, f"Mentions: {updated_goals[0]['mention_count']}")


# TEST 5: Weighted Priority Retrieval (RAG)
print("\n--- TEST 5: Weighted Priority Search ---")
# Search for CEO query
results_search = vector_memory.semantic_search("what is my CEO goal?")
test("Semantic search returned results", len(results_search) > 0)
if results_search:
    best = results_search[0]
    # Check if the goal matched
    test("Best match is the Goal entity", "Active Goal" in best["user_message"])
    # Calculate score using formula: similarity * weight * importance
    # Goal weight = 1.3, importance = 0.95.
    expected_score = best["similarity"] * 1.3 * best["importance_score"]
    test("Priority score calculated correctly", abs(best["score"] - expected_score) < 0.01, f"Expected: {expected_score:.4f}, Got: {best['score']:.4f}")

# TEST 6: Goal Completion
print("\n--- TEST 6: Goal Completion ---")
# Complete the goal we created earlier
active_goals = memory_manager.load_goals(status='active')
test("Goal is active before completion", len(active_goals) > 0 and active_goals[0]["status"] == "active")

memory_manager.update_goal_status(active_goals[0]["id"], "completed")
active_after = memory_manager.load_goals(status='active')
all_goals = memory_manager.load_goals()
completed_goals = [g for g in all_goals if g["status"] == "completed"]

test("Goal removed from active list after completion", len(active_after) == 0 or all(g["goal_text"] != "Become CEO" for g in active_after))
test("Goal exists with 'completed' status", any(g["goal_text"] == "Become CEO" and g["status"] == "completed" for g in completed_goals))


# RESULTS
print("\n" + "=" * 60)
passed = sum(results)
total = len(results)
if passed == total:
    print(f"  \033[32m ALL {total} TESTS PASSED \033[0m")
else:
    print(f"  \033[31m {passed}/{total} TESTS PASSED ({total - passed} FAILED) \033[0m")
print("=" * 60 + "\n")
sys.exit(0 if passed == total else 1)
