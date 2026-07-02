"""
Test Suite for Sprint 4: Graph Memory & Relationship Caching
============================================================
Validates database layers, automatic caching of top-3 nearest semantic neighbors,
cross-entity link creation, and NetworkX graph visualizer building/exporting.
"""

import os
import sys
import time

# Ensure we can import from the project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_manager
import vector_memory
import graph_visualizer

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
print("  PANDA Sprint 4 Graph Memory Test Suite")
print("=" * 60)

# Setup
print("\n  [Setup] Initializing database...")
memory_manager.initialize_memory()
session_id = "test_sprint4_session"

# Clear old test data if any
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM entity_links")
cursor.execute("DELETE FROM interactions WHERE session_id = ?", (session_id,))
cursor.execute("DELETE FROM goals WHERE session_id = ?", (session_id,))
cursor.execute("DELETE FROM projects WHERE session_id = ?", (session_id,))
cursor.execute("DELETE FROM preferences WHERE session_id = ?", (session_id,))
cursor.execute("DELETE FROM vector_memory")
conn.commit()
conn.close()

# TEST 1: Database Schema Check
print("\n--- TEST 1: Database Schema Check ---")
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(entity_links)")
cols_links = {row["name"] for row in cursor.fetchall()}
conn.close()

expected_fields = {"id", "source_table", "source_id", "target_table", "target_id", "similarity_score", "link_type", "created_at"}
test("entity_links table has correct columns", expected_fields.issubset(cols_links), f"Columns: {cols_links}")


# TEST 2: Explicit Edge Saving & Retrieval
print("\n--- TEST 2: Explicit Edge Saving & Retrieval ---")
link_id = memory_manager.save_entity_link(
    source_table="goals",
    source_id=1,
    target_table="projects",
    target_id=1,
    similarity_score=0.85,
    link_type="explicit_reference"
)

test("Entity link saved successfully", link_id > 0)

# Query links back
links_for_goal = memory_manager.get_links_for_entity("goals", 1)
test("Retrieve links for source entity", len(links_for_goal) > 0 and links_for_goal[0]["target_id"] == 1)

links_for_project = memory_manager.get_links_for_entity("projects", 1)
test("Retrieve links for target entity", len(links_for_project) > 0 and links_for_project[0]["source_id"] == 1)

all_links = memory_manager.get_all_links()
test("Retrieve all links", len(all_links) == 1)

# Clean explicit edge
conn = memory_manager._get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM entity_links")
conn.commit()
conn.close()


# TEST 3: Semantic Link Caching during Entity Creation
print("\n--- TEST 3: Semantic Link Caching ---")
# Generate embeddings warmup
vector_memory.get_embedding("warmup")

# Save three distinct goals
goal1_id = vector_memory.save_goal_semantic(
    session_id=session_id,
    goal_text="Become an expert Python programmer and developer",
    status="active"
)

goal2_id = vector_memory.save_goal_semantic(
    session_id=session_id,
    goal_text="Build web applications with Django and Python",
    status="active"
)

goal3_id = vector_memory.save_goal_semantic(
    session_id=session_id,
    goal_text="Learn Japanese sushi preparation techniques",
    status="active"
)

# Wait for cache/async execution
time.sleep(0.5)

links = memory_manager.get_all_links()
test("Links automatically created between semantically related entities", len(links) > 0)

# Check if Python programmer goal linked to Django web app goal
python_links = memory_manager.get_links_for_entity("goals", goal1_id)
has_python_link = any(
    (l["source_id"] == goal1_id and l["target_id"] == goal2_id) or 
    (l["source_id"] == goal2_id and l["target_id"] == goal1_id)
    for l in python_links
)
test("Python developer goal linked to Django web app goal", has_python_link)


# TEST 4: Interaction Semantic Link Caching
print("\n--- TEST 4: Interaction Caching ---")
# Save interaction related to Python
interaction_id = vector_memory.save_turn_semantic(
    session_id=session_id,
    user_message="Can you show me how to write a simple script in Python?",
    assistant_response="Sure, here is how you print Hello World in Python."
)

time.sleep(0.5)

# Check links for this interaction
int_links = memory_manager.get_links_for_entity("interactions", interaction_id)
test("Interaction created semantic links to related goals", len(int_links) > 0)
has_goal_link = any(l["target_table"] == "goals" for l in int_links)
test("Interaction links target goals table", has_goal_link)


# TEST 5: Graph Generation & Rendering
print("\n--- TEST 5: Graph Construction & Export ---")
G = graph_visualizer.build_networkx_graph()

test("NetworkX graph constructed successfully", G is not None)
test("Nodes populated in NetworkX graph", len(G.nodes) > 0)
test("Edges populated in NetworkX graph", len(G.edges) > 0)

# Check node attributes
sample_node_key = f"goals:{goal1_id}"
test("Node in graph has color attribute", "color" in G.nodes[sample_node_key])
test("Node in graph has label attribute", "label" in G.nodes[sample_node_key])
test("Node in graph has importance attribute", "importance" in G.nodes[sample_node_key])

# Export
html_output = "test_memory_graph.html"
export_path = graph_visualizer.export_graph_to_html(html_output)
test("Interactive HTML exported successfully", os.path.exists(export_path))
test("Interactive HTML file is non-empty", os.path.getsize(export_path) > 0)

# Cleanup output file
if os.path.exists(export_path):
    try:
        os.remove(export_path)
    except:
        pass

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
