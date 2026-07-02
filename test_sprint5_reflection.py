"""
Test Suite for Sprint 5: Episodic Memory & Reflection Engine
===========================================================
Validates database schemas, session summaries, routine reflections, 
cautious consolidation, learning from mistakes, synapse decay math, 
and automatic promotion.
"""

import os
import sys
import time
import datetime
from unittest.mock import MagicMock

# Ensure we can import from the project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_manager
import vector_memory
import reflection_engine

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
            except Exception as e:
                pass


print("\n" + "=" * 60)
print("  PANDA Sprint 5 Episodic & Reflection Test Suite")
print("=" * 60)

# Setup Test Database
print("\n  [Setup] Initializing isolated test database...")
cleanup_test_db()
TEST_DB_PATH = os.path.join(memory_manager.MEMORY_DIR, "panda_memory_test.db")
memory_manager.DB_PATH = TEST_DB_PATH

memory_manager.initialize_memory()
session_id = "test_sprint5_session"

# Mock Embeddings Model
vector_memory.get_embedding = lambda text: [0.1] * 384

# Mock Cosine Similarity Dynamic Control
default_similarity = 0.0
def mock_cosine_similarity(v1, v2):
    return default_similarity
vector_memory.cosine_similarity = mock_cosine_similarity

# Mock Ollama Client
mock_client = MagicMock()
reflection_engine._get_ollama_client = lambda: mock_client


# TEST 1: Database Schema Check
print("\n--- TEST 1: Database Schema Check ---")
conn = memory_manager._get_connection()
cursor = conn.cursor()

# Check tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = {row["name"] for row in cursor.fetchall()}

# Check columns
cursor.execute("PRAGMA table_info(goals)")
cols_goals = {row["name"] for row in cursor.fetchall()}
cursor.execute("PRAGMA table_info(projects)")
cols_projects = {row["name"] for row in cursor.fetchall()}
cursor.execute("PRAGMA table_info(preferences)")
cols_prefs = {row["name"] for row in cursor.fetchall()}

conn.close()

test("session_summaries table exists", "session_summaries" in tables)
test("reflections table exists", "reflections" in tables)
test("goals table has consolidated_to column", "consolidated_to" in cols_goals)
test("projects table has consolidated_to column", "consolidated_to" in cols_projects)
test("preferences table has consolidated_to column", "consolidated_to" in cols_prefs)


# TEST 2: Session Summarization
print("\n--- TEST 2: Session Summarization ---")
# Insert mock messages
memory_manager.save_message(session_id, "user", "I am working on developing the PANDA voice assistant today.")
memory_manager.save_message(session_id, "assistant", "That sounds like a great project. Let's write some python code.")

# Mock Ollama Response
mock_client.chat.return_value = {
    "message": {
        "content": '{"summary": "Aryan is developing PANDA voice assistant in Python.", "key_takeaways": ["Working on PANDA voice assistant", "Coding in Python"]}'
    }
}

summary_text = reflection_engine.summarize_session(session_id)
test("summarize_session returns correct text", summary_text == "Aryan is developing PANDA voice assistant in Python.")

# Verify saved to DB
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("SELECT * FROM session_summaries WHERE session_id = ?", (session_id,))
summary_row = cursor.fetchone()
cursor.execute("SELECT * FROM vector_memory WHERE source_table = 'session_summaries'")
vec_row = cursor.fetchone()
conn.close()

test("Summary saved to session_summaries table", summary_row is not None)
if summary_row:
    test("Key takeaways stored as valid JSON", "Working on PANDA" in summary_row["key_takeaways"])
test("Summary indexed in vector_memory", vec_row is not None)


# TEST 3: Pattern & Routine Reflections
print("\n--- TEST 3: Pattern & Routine Reflections ---")
# Mock Ollama Response
mock_client.chat.return_value = {
    "message": {
        "content": '{"reflections": [{"insight": "Aryan routinely codes in Python", "category": "routine", "importance": 0.85}]}'
    }
}

new_refs = reflection_engine.generate_reflections("daily")
test("generate_reflections returns list of new insights", len(new_refs) == 1 and new_refs[0] == "Aryan routinely codes in Python")

# Verify in DB
reflections = memory_manager.load_reflections()
test("Reflection saved in database", len(reflections) == 1 and reflections[0]["insight_text"] == "Aryan routinely codes in Python")
if reflections:
    test("Reflection has correct category and score", reflections[0]["category"] == "routine" and reflections[0]["importance_score"] == 0.85)

# Verify Duplicate & Automatic Promotion
# Running again with same output should trigger duplicate detection and boost importance
reflections_before = reflections[0]
new_refs_dup = reflection_engine.generate_reflections("daily")
reflections_after = memory_manager.load_reflections()

test("Duplicate reflection not duplicated in DB", len(reflections_after) == 1)
test("Duplicate reflection importance score boosted", reflections_after[0]["importance_score"] > reflections_before["importance_score"])


# TEST 4: Cautious Memory Consolidation
print("\n--- TEST 4: Cautious Memory Consolidation ---")
# Insert two goals that are similar
goal_id_1 = vector_memory.save_goal_semantic(session_id, "Become a skilled Python developer")
goal_id_2 = vector_memory.save_goal_semantic(session_id, "Become a professional Python programmer")

# Mock similarity high
default_similarity = 0.85

# Mock merge LLM response
mock_client.chat.return_value = {
    "message": {
        "content": "Become an expert Python programmer"
    }
}

merged_cnt = reflection_engine.consolidate_memories()
test("consolidate_memories merged the similar goals", merged_cnt == 1)

# Verify DB state
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("SELECT * FROM goals WHERE id = ?", (goal_id_1,))
g1 = dict(cursor.fetchone())
cursor.execute("SELECT * FROM goals WHERE id = ?", (goal_id_2,))
g2 = dict(cursor.fetchone())
cursor.execute("SELECT * FROM goals WHERE consolidated_to IS NULL ORDER BY id DESC LIMIT 1")
new_g = dict(cursor.fetchone())
conn.close()

test("Goal 1 points to new consolidated goal", g1["consolidated_to"] == new_g["id"])
test("Goal 2 points to new consolidated goal", g2["consolidated_to"] == new_g["id"])
test("New consolidated goal contains merged text", new_g["goal_text"] == "Become an expert Python programmer")

# Verify active memory search filters out consolidated entries
active_memories = memory_manager.load_all_memories_with_embeddings()
goal_ids_active = {m["source_id"] for m in active_memories if m["source_table"] == "goals"}
test("Active memories exclude consolidated Goal 1", goal_id_1 not in goal_ids_active)
test("Active memories exclude consolidated Goal 2", goal_id_2 not in goal_ids_active)
test("Active memories include new consolidated goal", new_g["id"] in goal_ids_active)

# Reset similarity
default_similarity = 0.0


# TEST 5: Learning from Mistakes
print("\n--- TEST 5: Learning from Mistakes ---")
# Insert mistake correction
corr_id = vector_memory.save_correction_semantic(session_id, "Assistant thought user uses Windows", "User uses Linux exclusively")

# Mock Ollama Response
mock_client.chat.return_value = {
    "message": {
        "content": '{"rules": ["PANDA should never assume user uses Windows; user uses Linux exclusively"]}'
    }
}

rules_cnt = reflection_engine.learn_from_mistakes()
test("learn_from_mistakes generated rules", rules_cnt == 1)

# Verify DB reflection saved
reflections = memory_manager.load_reflections()
corr_ref = next((r for r in reflections if r["category"] == "correction"), None)
test("Rule of action saved as correction reflection", corr_ref is not None)
if corr_ref:
    test("Correction reflection has correct rule text", corr_ref["insight_text"] == "PANDA should never assume user uses Windows; user uses Linux exclusively")
    test("Correction reflection has high initial importance score (0.95)", corr_ref["importance_score"] == 0.95)


# TEST 6: Differentiated Synapse Decay
print("\n--- TEST 6: Differentiated Synapse Decay ---")
# Set up database with entries having old timestamps (e.g. 5 days ago)
five_days_ago = (datetime.datetime.now() - datetime.timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")

conn = memory_manager._get_connection()
cursor = conn.cursor()

# Reset database content for decay test
cursor.execute("DELETE FROM interactions")
cursor.execute("DELETE FROM projects")
cursor.execute("DELETE FROM goals")
cursor.execute("DELETE FROM preferences")
cursor.execute("DELETE FROM reflections")
cursor.execute("DELETE FROM corrections")

# Insert old entries
cursor.execute("""
    INSERT INTO interactions (session_id, user_message, assistant_response, importance_score, timestamp)
    VALUES (?, ?, ?, 0.8, ?)
""", (session_id, "hello", "hi", five_days_ago))
int_id = cursor.lastrowid

cursor.execute("""
    INSERT INTO projects (session_id, project_name, description, importance_score, extracted_from_interaction_id, confidence, mention_count, created_at, updated_at)
    VALUES (?, ?, ?, 0.8, ?, 1.0, 1, ?, ?)
""", (session_id, "DecayProj", "test project", int_id, five_days_ago, five_days_ago))
proj_id = cursor.lastrowid

cursor.execute("""
    INSERT INTO goals (session_id, goal_text, status, importance_score, extracted_from_interaction_id, confidence, mention_count, created_at, updated_at)
    VALUES (?, ?, 'active', 0.8, ?, 1.0, 1, ?, ?)
""", (session_id, "DecayGoal", int_id, five_days_ago, five_days_ago))
goal_id = cursor.lastrowid

cursor.execute("""
    INSERT INTO preferences (session_id, preference_text, importance_score, extracted_from_interaction_id, confidence, mention_count, created_at, updated_at)
    VALUES (?, ?, 0.8, ?, 1.0, 1, ?, ?)
""", (session_id, "DecayPref", int_id, five_days_ago, five_days_ago))
pref_id = cursor.lastrowid

cursor.execute("""
    INSERT INTO reflections (reflection_type, insight_text, category, importance_score, created_at)
    VALUES ('daily', 'DecayInsight', 'routine', 0.8, ?)
""", (five_days_ago,))
ref_id = cursor.lastrowid

cursor.execute("""
    INSERT INTO corrections (session_id, mistake_context, corrected_fact, importance_score, extracted_from_interaction_id, confidence, mention_count, created_at, updated_at)
    VALUES (?, ?, ?, 0.8, ?, 1.0, 1, ?, ?)
""", (session_id, "mistake", "correction", int_id, five_days_ago, five_days_ago))
corr_id = cursor.lastrowid

conn.commit()
conn.close()

# Apply decay
reflection_engine.apply_memory_decay()

# Load decayed entries
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("SELECT importance_score FROM interactions WHERE id = ?", (int_id,))
score_int = cursor.fetchone()["importance_score"]
cursor.execute("SELECT importance_score FROM projects WHERE id = ?", (proj_id,))
score_proj = cursor.fetchone()["importance_score"]
cursor.execute("SELECT importance_score FROM goals WHERE id = ?", (goal_id,))
score_goal = cursor.fetchone()["importance_score"]
cursor.execute("SELECT importance_score FROM preferences WHERE id = ?", (pref_id,))
score_pref = cursor.fetchone()["importance_score"]
cursor.execute("SELECT importance_score FROM reflections WHERE id = ?", (ref_id,))
score_ref = cursor.fetchone()["importance_score"]
cursor.execute("SELECT importance_score FROM corrections WHERE id = ?", (corr_id,))
score_corr = cursor.fetchone()["importance_score"]
conn.close()

# Expected scores: score * (1 - rate)^5
# Rates: interactions=0.035, projects=0.015, goals=0.005, preferences=0.005, reflections=0.010, corrections=0
expected_int = round(0.8 * ((1 - 0.035) ** 5), 4)
expected_proj = round(0.8 * ((1 - 0.015) ** 5), 4)
expected_goal = round(0.8 * ((1 - 0.005) ** 5), 4)
expected_pref = round(0.8 * ((1 - 0.005) ** 5), 4)
expected_ref = round(0.8 * ((1 - 0.010) ** 5), 4)
expected_corr = 0.8 # corrections never decay

test("Interactions decay score matches formula", abs(score_int - expected_int) < 0.0001, f"Expected: {expected_int}, Got: {score_int}")
test("Projects decay score matches formula", abs(score_proj - expected_proj) < 0.0001, f"Expected: {expected_proj}, Got: {score_proj}")
test("Goals decay score matches formula", abs(score_goal - expected_goal) < 0.0001, f"Expected: {expected_goal}, Got: {score_goal}")
test("Preferences decay score matches formula", abs(score_pref - expected_pref) < 0.0001, f"Expected: {expected_pref}, Got: {score_pref}")
test("Reflections decay score matches formula", abs(score_ref - expected_ref) < 0.0001, f"Expected: {expected_ref}, Got: {score_ref}")
test("Corrections DO NOT decay", score_corr == expected_corr, f"Expected: {expected_corr}, Got: {score_corr}")


# TEST 7: Automatic Promotion (Boost Mention)
print("\n--- TEST 7: Automatic Promotion (Boost Mention) ---")
# Reset mention counts and importance scores to baseline (0.5)
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("UPDATE goals SET importance_score = 0.5, mention_count = 1 WHERE id = ?", (goal_id,))
cursor.execute("UPDATE projects SET importance_score = 0.5, mention_count = 1 WHERE id = ?", (proj_id,))
cursor.execute("UPDATE preferences SET importance_score = 0.5, mention_count = 1 WHERE id = ?", (pref_id,))
cursor.execute("UPDATE corrections SET importance_score = 0.5, mention_count = 1 WHERE id = ?", (corr_id,))
conn.commit()
conn.close()

# Boost mentions
memory_manager.increment_goal_mention(goal_id)
memory_manager.increment_project_mention(proj_id)
memory_manager.increment_preference_mention(pref_id)
memory_manager.increment_correction_mention(corr_id)

# Load boosted records
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("SELECT importance_score, mention_count, updated_at FROM goals WHERE id = ?", (goal_id,))
g_boost = dict(cursor.fetchone())
cursor.execute("SELECT importance_score, mention_count, updated_at FROM projects WHERE id = ?", (proj_id,))
p_boost = dict(cursor.fetchone())
cursor.execute("SELECT importance_score, mention_count, updated_at FROM preferences WHERE id = ?", (pref_id,))
pr_boost = dict(cursor.fetchone())
cursor.execute("SELECT importance_score, mention_count, updated_at FROM corrections WHERE id = ?", (corr_id,))
c_boost = dict(cursor.fetchone())
conn.close()

test("Goal mention incremented and importance boosted by 0.10", g_boost["mention_count"] == 2 and abs(g_boost["importance_score"] - 0.60) < 0.0001)
test("Project mention incremented and importance boosted by 0.10", p_boost["mention_count"] == 2 and abs(p_boost["importance_score"] - 0.60) < 0.0001)
test("Preference mention incremented and importance boosted by 0.10", pr_boost["mention_count"] == 2 and abs(pr_boost["importance_score"] - 0.60) < 0.0001)
test("Correction mention incremented and importance boosted by 0.10", c_boost["mention_count"] == 2 and abs(c_boost["importance_score"] - 0.60) < 0.0001)

# Verify updated_at is refreshed to current time
now_prefix = datetime.datetime.now().strftime("%Y-%m-%d")
test("Goal updated_at is refreshed to today", g_boost["updated_at"].startswith(now_prefix))


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
    print(f"  \033[32m ALL {total} TESTS PASSED \033[0m")
else:
    print(f"  \033[31m {passed}/{total} TESTS PASSED ({total - passed} FAILED) \033[0m")
print("=" * 60 + "\n")
sys.exit(0 if passed == total else 1)
