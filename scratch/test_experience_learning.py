import sys
import os
import json

# Add parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import memory_manager
from vector_memory import save_trajectory_semantic, semantic_search_trajectories

def main():
    print("Initializing memory...")
    memory_manager.initialize_memory()
    
    # Clean up any existing test trajectories for clean run
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM task_trajectories WHERE goal LIKE '%TEST:%'")
    cursor.execute("DELETE FROM vector_memory WHERE content_text LIKE '%TEST:%'")
    conn.commit()
    conn.close()

    print("\n--- Test 1: Save Trajectory ---")
    mock_goal = "TEST: Open Notepad"
    mock_steps = [
        {"step": 1, "action": "system_search", "parameters": {"query": "notepad"}, "result": "I searched the system for 'notepad' and opened it."}
    ]
    mock_status = "success"
    mock_summary = "Opening notepad works best by using taskbar search instead of clicking desktop icons."
    
    traj_id = save_trajectory_semantic(
        goal=mock_goal,
        steps_json=json.dumps(mock_steps),
        status=mock_status,
        summary=mock_summary
    )
    print(f"Saved test trajectory. Row ID: {traj_id}")
    
    # Load and verify
    record = memory_manager.load_trajectory_by_id(traj_id)
    assert record is not None, "Failed to load trajectory from DB"
    assert record["goal"] == mock_goal, "Goal mismatch"
    assert record["status"] == mock_status, "Status mismatch"
    print("Test 1 Passed: Trajectory saved and loaded successfully!")

    print("\n--- Test 2: Semantic Search Trajectories ---")
    search_query = "TEST: start notepad" # slightly different wording to test semantic similarity
    results = semantic_search_trajectories(search_query, top_k=1)
    
    assert len(results) > 0, "No search results returned"
    match = results[0]
    print(f"Match found! Goal: '{match['goal']}' | Similarity: {match['similarity']}")
    assert match["goal"] == mock_goal, f"Expected goal '{mock_goal}', got '{match['goal']}'"
    print("Test 2 Passed: Semantic search successfully retrieved the similar task!")

    print("\n[OK] All tests passed successfully!")

if __name__ == "__main__":
    main()
