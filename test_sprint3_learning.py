"""
Test Suite for Sprint 3: Preferences & Correction Memory
=========================================================
Validates database schemas, preference saving/retrieval, correction saving/retrieval,
mention count incrementing, priority ranking weights (RAG), and FSM integration.
"""

import os
import sys
import time

# Ensure we can import from the project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_manager
import vector_memory
import fusion_layer

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
print("  PANDA Sprint 3 Learning & Identity Test Suite")
print("=" * 60)

# Setup
print("\n  [Setup] Initializing database...")
memory_manager.initialize_memory()
session_id = "test_sprint3_session"

# Clear old test data if any
conn = memory_manager._get_connection()
cursor = conn.cursor()
test_sessions = [session_id, "test_dedup_session", "test_extract_session", "test_extract_session_2"]
for sid in test_sessions:
    # Delete vector_memory FIRST (while source rows still exist for subquery)
    cursor.execute("""
        DELETE FROM vector_memory WHERE
            (source_table = 'interactions' AND source_id IN (SELECT id FROM interactions WHERE session_id = ?))
            OR (source_table = 'preferences' AND source_id IN (SELECT id FROM preferences WHERE session_id = ?))
            OR (source_table = 'corrections' AND source_id IN (SELECT id FROM corrections WHERE session_id = ?))
            OR (source_table = 'goals' AND source_id IN (SELECT id FROM goals WHERE session_id = ?))
            OR (source_table = 'projects' AND source_id IN (SELECT id FROM projects WHERE session_id = ?))
    """, (sid, sid, sid, sid, sid))
    # Then delete source rows
    cursor.execute("DELETE FROM interactions WHERE session_id = ?", (sid,))
    cursor.execute("DELETE FROM preferences WHERE session_id = ?", (sid,))
    cursor.execute("DELETE FROM corrections WHERE session_id = ?", (sid,))
    cursor.execute("DELETE FROM goals WHERE session_id = ?", (sid,))
    cursor.execute("DELETE FROM projects WHERE session_id = ?", (sid,))
cursor.execute("""
    DELETE FROM vector_memory WHERE content_text LIKE 'Correction: %'
    OR content_text = 'Likes dark theme'
    OR content_text = 'I prefer Python'
    OR content_text = 'I love coding using Python language'
    OR content_text = 'Wait, I use Llama instead of GPT'
    OR content_text = 'I write GPT applications'
    OR content_text LIKE 'Active Goal:%'
    OR content_text LIKE 'Project DataPipeline%'
    OR content_text = 'I prefer dark mode in all IDEs'
    OR content_text = 'become a machine learning researcher'
    OR content_text = 'I want to become a software engineer'
    OR content_text = 'I want to learn Japanese cooking techniques'
""")
conn.commit()
conn.close()

# TEST 1: Database Schema Check
print("\n--- TEST 1: Database Schema Check ---")
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(preferences)")
cols_pref = {row["name"] for row in cursor.fetchall()}
cursor.execute("PRAGMA table_info(corrections)")
cols_corr = {row["name"] for row in cursor.fetchall()}
conn.close()

expected_pref = {"id", "session_id", "preference_text", "importance_score", 
                 "extracted_from_interaction_id", "confidence", "mention_count", 
                 "created_at", "updated_at"}
expected_corr = {"id", "session_id", "mistake_context", "corrected_fact", "importance_score", 
                 "extracted_from_interaction_id", "confidence", "mention_count", 
                 "created_at", "updated_at"}

test("preferences table has correct columns", expected_pref.issubset(cols_pref), f"Columns: {cols_pref}")
test("corrections table has correct columns", expected_corr.issubset(cols_corr), f"Columns: {cols_corr}")


# TEST 2: Preference and Correction Saving
print("\n--- TEST 2: Structured Saving & Retrieval ---")
dummy_int_id = memory_manager.save_interaction(
    session_id=session_id,
    user_message="I like python and dark themes",
    assistant_response="Understood, I will remember that.",
    importance_score=0.3
)

# Save preference
pref_id = vector_memory.save_preference_semantic(
    session_id=session_id,
    preference_text="I prefer Python",
    extracted_from=dummy_int_id,
    confidence=0.9
)

# Save correction
corr_id = vector_memory.save_correction_semantic(
    session_id=session_id,
    mistake_context="I use GPT",
    corrected_fact="I use Llama",
    extracted_from=dummy_int_id,
    confidence=1.0
)

# Verify preferences loaded
prefs = memory_manager.load_preferences()
test("Preference saved and retrieved correctly", len(prefs) > 0 and prefs[0]["preference_text"] == "I prefer Python")
if prefs:
    test("Preference extra data matches", prefs[0]["confidence"] == 0.9 and prefs[0]["mention_count"] == 1)

# Verify corrections loaded
corrs = memory_manager.load_corrections()
test("Correction saved and retrieved correctly", len(corrs) > 0 and corrs[0]["mistake_context"] == "I use GPT")
if corrs:
    test("Correction extra data matches", corrs[0]["corrected_fact"] == "I use Llama" and corrs[0]["mention_count"] == 1)


# TEST 3: Indexing in Vector Memory
print("\n--- TEST 3: Vector Memory Indexing ---")
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("SELECT source_table, source_id, content_text FROM vector_memory WHERE source_table IN ('preferences', 'corrections')")
indexed_rows = cursor.fetchall()
conn.close()

pref_indexed = any(row["source_table"] == "preferences" and row["source_id"] == pref_id for row in indexed_rows)
corr_indexed = any(row["source_table"] == "corrections" and row["source_id"] == corr_id for row in indexed_rows)

test("Preference indexed in vector memory", pref_indexed)
test("Correction indexed in vector memory", corr_indexed)
if indexed_rows:
    try:
        corr_row = next(r for r in indexed_rows if r["source_table"] == "corrections" and r["source_id"] == corr_id)
        test("Correction indexed combined string format", corr_row["content_text"] == "Correction: Previously thought 'I use GPT', but the truth is 'I use Llama'")
    except StopIteration:
        test("Correction indexed combined string format", False, "Correction row not found in indexed rows")


# TEST 4: Dynamic Mention Count Updates
print("\n--- TEST 4: Dynamic Mention Count Updates ---")
# Call save_turn_semantic with a message highly similar to "I prefer Python"
vector_memory.save_turn_semantic(session_id, "I love coding using Python language", "Yes, Python is great!")

# Call save_turn_semantic with a message highly similar to the correction mistake context/corrected fact
vector_memory.save_turn_semantic(session_id, "Wait, I use Llama instead of GPT", "Noted, I updated my memory.")

time.sleep(0.5)

updated_prefs = memory_manager.load_preferences()
updated_corrs = memory_manager.load_corrections()

test("Preference mention count incremented dynamically", updated_prefs[0]["mention_count"] == 2, f"Mentions: {updated_prefs[0]['mention_count']}")
test("Correction mention count incremented dynamically", updated_corrs[0]["mention_count"] == 2, f"Mentions: {updated_corrs[0]['mention_count']}")


# TEST 5: Weighted Priority RAG Search
print("\n--- TEST 5: Weighted Priority Search (RAG) ---")
# Perform semantic search on python query (top_k=5 to include preference alongside interactions)
results_pref = vector_memory.semantic_search("what programming language do I like?", top_k=5)
test("Preference is retrieved on language query", len(results_pref) > 0)
if results_pref:
    pref_found = any("User Preference" in item["user_message"] for item in results_pref)
    test("Preference is formatted correctly for RAG", pref_found, f"Matches: {[r['user_message'] for r in results_pref]}")

# Search correction to check overriding weight (corrections: 1.5x, interactions: 1.0x)
# Add an interaction memory that represents the mistake:
mistake_interaction_id = memory_manager.save_interaction(
    session_id=session_id,
    user_message="I write GPT applications",
    assistant_response="Awesome, GPT is powerful.",
    importance_score=0.3
)
memory_manager.save_embedding(
    source_table="interactions",
    source_id=mistake_interaction_id,
    content_text="I write GPT applications",
    embedding=vector_memory.get_embedding("I write GPT applications")
)

results_corr = vector_memory.semantic_search("do I use GPT or Llama?")
test("RAG search returned results for correction query", len(results_corr) > 0)
if results_corr:
    best_match = results_corr[0]
    test("Correction is ranked first overriding the mistake", "Previously thought" in best_match["user_message"])
    # Verify score calculation: similarity * entity_weight * importance
    # Correction entity weight is 1.5. Importance score is calculated or default.
    expected_score = best_match["similarity"] * 1.5 * best_match["importance_score"]
    test("Correction priority score calculated correctly", abs(best_match["score"] - expected_score) < 0.01, f"Expected: {expected_score:.4f}, Got: {best_match['score']:.4f}")


# TEST 6: FSM Integration Check
print("\n--- TEST 6: FSM Integration ---")
# Reset FSM
fusion_layer.cancel()

# Test preference_add FSM slots
res_pref = fusion_layer.fuse("preference_add", {}, "I prefer Python")
test("preference_add FSM transitions to awaiting slot if preference is missing", res_pref["status"] == "missing" and res_pref["current_state"] == "awaiting_slot")

res_pref_filled = fusion_layer.fuse("preference_add", {"preference": "I prefer Python"}, "I prefer Python")
test("preference_add FSM executes when preference is provided", res_pref_filled["status"] == "ready" and res_pref_filled["action"] == "preference_add")

# Test correction_add FSM slots
res_corr = fusion_layer.fuse("correction_add", {}, "Correction")
test("correction_add FSM transitions to awaiting slot if slots missing", res_corr["status"] == "missing" and res_corr["current_state"] == "awaiting_slot")

res_corr_partial = fusion_layer.fuse("correction_add", {"mistake": "I use GPT"}, "Correction")
test("correction_add FSM still awaiting slot if only mistake is provided", res_corr_partial["status"] == "missing" and res_corr_partial["current_state"] == "awaiting_slot")

res_corr_filled = fusion_layer.fuse("correction_add", {"mistake": "I use GPT", "correction": "I use Llama"}, "Correction")
test("correction_add FSM executes when all slots filled", res_corr_filled["status"] == "ready" and res_corr_filled["action"] == "correction_add")


# TEST 7: Session ID Format (Pre-Sprint 4 Fix)
print("\n--- TEST 7: Session ID Format (Timestamp-Based) ---")
import re
new_session_id = memory_manager.generate_session_id()
test("Session ID starts with 'session_'", new_session_id.startswith("session_"))
# Format: session_YYYYMMDD_HHMMSS_ffffff
pattern = r"^session_\d{8}_\d{6}_\d{6}$"
test("Session ID matches timestamp format (session_YYYYMMDD_HHMMSS_ffffff)", bool(re.match(pattern, new_session_id)), f"Got: {new_session_id}")

# Generate two IDs rapidly — they should be different (microsecond suffix)
id_a = memory_manager.generate_session_id()
id_b = memory_manager.generate_session_id()
test("Two rapid session IDs are unique (no collision)", id_a != id_b, f"A: {id_a}, B: {id_b}")


# TEST 8: Mention Cooldown (Pre-Sprint 4 Fix)
print("\n--- TEST 8: Mention Cooldown (Session-Based) ---")
# Clear the tracker for clean test
vector_memory._session_mention_tracker.clear()

cooldown_session = "test_cooldown_session"

# First call should return False (not yet mentioned) and mark it
was_mentioned_1 = vector_memory._has_been_mentioned_this_session(cooldown_session, "goal", 999)
test("First mention returns False (allow increment)", was_mentioned_1 == False)

# Second call should return True (already mentioned this session)
was_mentioned_2 = vector_memory._has_been_mentioned_this_session(cooldown_session, "goal", 999)
test("Second mention returns True (skip increment)", was_mentioned_2 == True)

# Different entity in same session should be independent
was_mentioned_3 = vector_memory._has_been_mentioned_this_session(cooldown_session, "project", 888)
test("Different entity returns False (independent tracking)", was_mentioned_3 == False)

# Different session should be fresh
different_session = "test_cooldown_session_2"
was_mentioned_4 = vector_memory._has_been_mentioned_this_session(different_session, "goal", 999)
test("Same entity in new session returns False (fresh session)", was_mentioned_4 == False)


# TEST 9: Duplicate Detection (Pre-Sprint 4 Fix)
print("\n--- TEST 9: Duplicate Detection ---")
# Clear cooldown for clean test
vector_memory._session_mention_tracker.clear()

dedup_session = "test_dedup_session"

# Save a goal
goal_text_1 = "I want to become a software engineer"
goal_id_1 = vector_memory.save_goal_semantic(dedup_session, goal_text_1)
test("Initial goal saved successfully", goal_id_1 is not None)

# Load and check baseline mention count
goals_before = memory_manager.load_goals(status='active')
goal_1_data = next((g for g in goals_before if g["id"] == goal_id_1), None)
test("Goal exists in database", goal_1_data is not None)
baseline_mentions = goal_1_data["mention_count"] if goal_1_data else 0

# Now test duplicate detection with memory_extractor
import memory_extractor

# Create an embedding for a near-duplicate goal
duplicate_text = "I want to become a software developer"
dup_emb = vector_memory.get_embedding(duplicate_text)
test("Embedding generated for duplicate text", dup_emb is not None)

# The two texts are semantically very similar — check
if dup_emb:
    orig_emb = vector_memory.get_embedding(goal_text_1)
    sim = vector_memory.cosine_similarity(dup_emb, orig_emb)
    test(f"Duplicate similarity is high (>= 0.85)", sim >= memory_extractor.DUPLICATE_THRESHOLD, f"Similarity: {sim:.3f}")

    # Run duplicate detection
    is_dup = memory_extractor._is_duplicate_goal(duplicate_text, dup_emb, dedup_session)
    test("Duplicate detector identifies near-duplicate goal", is_dup == True)

    # Verify mention count was incremented
    goals_after = memory_manager.load_goals(status='active')
    goal_1_after = next((g for g in goals_after if g["id"] == goal_id_1), None)
    if goal_1_after:
        test("Mention count incremented on duplicate", goal_1_after["mention_count"] > baseline_mentions,
             f"Before: {baseline_mentions}, After: {goal_1_after['mention_count']}")

# Test a genuinely different goal — should NOT be duplicate
different_text = "I want to learn Japanese cooking techniques"
diff_emb = vector_memory.get_embedding(different_text)
if diff_emb:
    is_dup_2 = memory_extractor._is_duplicate_goal(different_text, diff_emb, dedup_session)
    test("Genuinely different goal is NOT a duplicate", is_dup_2 == False)


# TEST 10: Memory Extraction (Mocked LLM)
print("\n--- TEST 10: Memory Extraction Pipeline (Mocked LLM) ---")
# We mock extract_memory_entities() since Ollama may not be running
# but test the full process_extracted_entities() pipeline

extract_session = "test_extract_session"
vector_memory._session_mention_tracker.clear()

# Clean up from previous test runs
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM goals WHERE session_id = ?", (extract_session,))
cursor.execute("DELETE FROM projects WHERE session_id = ?", (extract_session,))
cursor.execute("DELETE FROM preferences WHERE session_id = ?", (extract_session,))
cursor.execute("DELETE FROM corrections WHERE session_id = ?", (extract_session,))
conn.commit()
conn.close()

# Simulate what the LLM would return
mock_entities = {
    "goals": ["become a machine learning researcher"],
    "projects": [{"name": "DataPipeline", "description": "automated data processing pipeline"}],
    "preferences": ["I prefer dark mode in all IDEs"],
    "corrections": []
}

# Run the processing pipeline (bypasses LLM, uses the save functions directly)
fake_interaction_id = 9999
memory_extractor.process_extracted_entities(extract_session, mock_entities, fake_interaction_id)

# Verify the entities were saved
extract_goals = memory_manager.load_goals(status='active')
extract_goal_found = any("machine learning researcher" in g["goal_text"] for g in extract_goals)
test("Extracted goal saved to database", extract_goal_found)

extract_projects = memory_manager.load_projects()
extract_proj_found = any(p["project_name"] == "DataPipeline" for p in extract_projects)
test("Extracted project saved to database", extract_proj_found)

extract_prefs = memory_manager.load_preferences()
extract_pref_found = any("dark mode" in p["preference_text"] for p in extract_prefs)
test("Extracted preference saved to database", extract_pref_found)

# Now run the SAME mock entities again — should trigger duplicate detection, not insert
goals_count_before = len([g for g in memory_manager.load_goals(status='active') if "machine learning researcher" in g["goal_text"]])

# Clear session tracker to allow the dedup logic to run fully (simulating a new session)
vector_memory._session_mention_tracker.clear()
memory_extractor.process_extracted_entities("test_extract_session_2", mock_entities, 10000)

goals_count_after = len([g for g in memory_manager.load_goals(status='active') if "machine learning researcher" in g["goal_text"]])
test("Duplicate entities are NOT inserted again (dedup works)", goals_count_before == goals_count_after,
     f"Before: {goals_count_before} row(s), After: {goals_count_after} row(s)")


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
