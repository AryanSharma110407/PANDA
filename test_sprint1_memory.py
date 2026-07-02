"""
Test Suite for Sprint 1: Raw & Semantic Memory
==============================================
Validates database migration, embedding generation, importance calculations,
and prioritized semantic search correctness.
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


def cleanup_test_db():
    for filename in ["panda_memory_test.db", "panda_memory_test.db-wal", "panda_memory_test.db-shm"]:
        path = os.path.join(memory_manager.MEMORY_DIR, filename)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


print("\n" + "=" * 60)
print("  PANDA Sprint 1 Memory Test Suite")
print("=" * 60)

# Setup
print("\n  [Setup] Initializing isolated test database...")
cleanup_test_db()
TEST_DB_PATH = os.path.join(memory_manager.MEMORY_DIR, "panda_memory_test.db")
memory_manager.DB_PATH = TEST_DB_PATH

memory_manager.initialize_memory()
session_id = "test_sprint1_session"

# TEST 1: Schema Checks
print("\n--- TEST 1: Database Schema Check ---")
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(interactions)")
cols_int = {row["name"] for row in cursor.fetchall()}
cursor.execute("PRAGMA table_info(vector_memory)")
cols_vec = {row["name"] for row in cursor.fetchall()}
conn.close()

test("interactions table has correct columns", 
     {"id", "session_id", "user_message", "assistant_response", "importance_score", "timestamp"}.issubset(cols_int),
     f"Columns: {cols_int}")

test("vector_memory table has correct columns", 
     {"id", "source_table", "source_id", "content_text", "embedding"}.issubset(cols_vec),
     f"Columns: {cols_vec}")


# TEST 2: Local Embedding Generation
print("\n--- TEST 2: Local Embedding Generation ---")
# Warmup the model (first call loads it into memory)
vector_memory.get_embedding("Warmup sentence to load model")

start_time = time.perf_counter()
emb = vector_memory.get_embedding("Test sentence for embedding generation")
elapsed = time.perf_counter() - start_time

test("Embedding generated successfully", isinstance(emb, list) and len(emb) == 384)
test("Embedding generation completes quickly (< 2.0s)", elapsed < 2.0, f"Time taken: {elapsed:.3f}s")


# TEST 3: Heuristic Importance Scores
print("\n--- TEST 3: Heuristic Importance Score Checks ---")
greeting_imp = vector_memory.calculate_importance("hello there panda", "Hello! How can I help you today?")
normal_imp = vector_memory.calculate_importance("what is python language?", "Python is a high-level programming language.")
project_imp = vector_memory.calculate_importance("I am building a python voice assistant called Alya", "Alya sounds like an exciting project!")
goal_imp = vector_memory.calculate_importance("My dream is to work at Microsoft and become a CEO", "That is an amazing long-term goal!")

test("Greeting importance is low", greeting_imp == 0.05, f"Score: {greeting_imp}")
test("Normal question importance is moderate", normal_imp == 0.30, f"Score: {normal_imp}")
test("Project importance is high", project_imp == 0.75, f"Score: {project_imp}")
test("Goal importance is maximum", goal_imp == 0.95, f"Score: {goal_imp}")


# TEST 4: Semantic Saving and Retrieval
print("\n--- TEST 4: Semantic Saving & Retrieval (RAG) ---")

# Save a few sample interactions
vector_memory.save_turn_semantic(session_id, "hello bot", "Hi there!")
vector_memory.save_turn_semantic(session_id, "I want to become a CEO and work at Microsoft", "Becoming CEO at Microsoft is a great target.")
vector_memory.save_turn_semantic(session_id, "how do I cook lasagna?", "You need pasta sheets, beef sauce, and cheese.")

# Perform semantic search
results_search = vector_memory.semantic_search("what are my career goals?")

test("Semantic search returned results", len(results_search) > 0)
if results_search:
    best_match = results_search[0]
    test("Semantic search matched the career goals context", 
         "become a CEO" in best_match["user_message"], 
         f"Best match content: '{best_match['user_message']}' (similarity: {best_match['similarity']})")
    
    # Check if lasagna is excluded or ranked lower due to low relevance
    lasagna_found = any("lasagna" in item["user_message"] for item in results_search)
    test("Unrelated content (lasagna) was not returned in top results", not lasagna_found)


# RESULTS
print("\n" + "=" * 60)
passed = sum(results)
total = len(results)
cleanup_test_db()
if passed == total:
    print(f"  \033[32m ALL {total} TESTS PASSED \033[0m")
else:
    print(f"  \033[31m {passed}/{total} TESTS PASSED ({total - passed} FAILED) \033[0m")
print("=" * 60 + "\n")
sys.exit(0 if passed == total else 1)
