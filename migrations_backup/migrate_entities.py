"""
✨ PANDA — Retroactive Entity Extraction Script
==============================================
Runs LLM-based entity extraction on historical interactions using the remote
Ollama LLaMA model. Automatically deduplicates and populates:
- goals
- projects
- preferences
- corrections
And updates the memory graph automatically at the end.

Features:
- Unicode stdout safety for Windows (avoids emoji print crashes)
- Fail-safe resume tracking (skips already processed interactions)
"""

import os
import sys
import sqlite3
from dotenv import load_dotenv

# Force stdout to UTF-8 on Windows to safely print emojis without encoding crashes
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables (critical for the ngrok OLLAMA_URL)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

import memory_manager
import vector_memory
import memory_extractor
import graph_visualizer

KEYWORDS = [
    # Goals
    "goal", "dream", "career", "become", "achieve", "learn", "aim", "target", "hope to", "plan to", "want to", "want a", "want be", "wish", "desire",
    # Projects
    "project", "build", "coding", "code", "programming", "develop", "implement", "app ", "software", "system", "alya", "assistant", "bot", "tool",
    # Preferences
    "prefer", "like", "love", "enjoy", "hate", "dislike", "favorite", "choice", "choose",
    # Corrections
    "actually", "correction", "wrong", "mistake", "correct", "update", "no I meant", "incorrect", "instead"
]

def run_extraction():
    print("==================================================")
    print("   PANDA RETROACTIVE ENTITY EXTRACTION PIPELINE")
    print("==================================================")
    
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model_name = os.getenv("MODEL_NAME", "llama3.1:8b")
    print(f"Ollama Target URL: {ollama_url}")
    print(f"Ollama Model Name: {model_name}\n")

    db_path = memory_manager.DB_PATH
    if not os.path.exists(db_path):
        print("Error: Database file does not exist!")
        return

    # Set up processed interaction file for resume capability
    processed_file = os.path.join(os.path.dirname(db_path), "processed_interactions.txt")
    processed_ids = set()
    if os.path.exists(processed_file):
        with open(processed_file, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str.isdigit():
                    processed_ids.add(int(line_str))
        print(f"Resuming: Loaded {len(processed_ids)} already processed interaction IDs from tracker.")

    conn = memory_manager._get_connection()
    cursor = conn.cursor()

    # Load all interactions
    cursor.execute("SELECT id, session_id, user_message, assistant_response, importance_score FROM interactions ORDER BY id ASC")
    interactions = [dict(row) for row in cursor.fetchall()]
    print(f"Loaded {len(interactions)} interactions from database.")

    # Filter interactions containing keywords
    to_process = []
    for item in interactions:
        interaction_id = item["id"]
        # Skip if already processed in a previous interrupted run
        if interaction_id in processed_ids:
            continue
            
        combined_text = (item["user_message"] + " " + item["assistant_response"]).lower()
        if any(kw in combined_text for kw in KEYWORDS):
            to_process.append(item)

    print(f"Found {len(to_process)} remaining interactions with potential entities to extract.")
    print(f"Skipping {len(interactions) - len(to_process) - len(processed_ids)} irrelevant conversational turns.\n")

    # Keep track of extraction stats
    total_goals_extracted = 0
    total_projects_extracted = 0
    total_preferences_extracted = 0
    total_corrections_extracted = 0
    processed_count = 0

    # Load goals/projects counts before starting
    cursor.execute("SELECT COUNT(*) FROM goals")
    goals_before = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM projects")
    projects_before = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM preferences")
    preferences_before = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM corrections")
    corrections_before = cursor.fetchone()[0]

    for idx, item in enumerate(to_process):
        interaction_id = item["id"]
        session_id = item["session_id"]
        u_msg = item["user_message"]
        a_resp = item["assistant_response"]

        print(f"[{idx+1}/{len(to_process)}] Processing Interaction ID {interaction_id} (Session: {session_id})...")
        print(f"  User: '{u_msg[:60]}...'")
        print(f"  Asst: '{a_resp[:60]}...'")

        # Run extraction
        try:
            entities = memory_extractor.extract_memory_entities(u_msg, a_resp)
            if entities:
                goals = entities.get("goals", [])
                projects = entities.get("projects", [])
                preferences = entities.get("preferences", [])
                corrections = entities.get("corrections", [])

                extracted_any = False
                if goals:
                    print(f"    -> Extracted Goals: {goals}")
                    total_goals_extracted += len(goals)
                    extracted_any = True
                if projects:
                    print(f"    -> Extracted Projects: {projects}")
                    total_projects_extracted += len(projects)
                    extracted_any = True
                if preferences:
                    print(f"    -> Extracted Preferences: {preferences}")
                    total_preferences_extracted += len(preferences)
                    extracted_any = True
                if corrections:
                    print(f"    -> Extracted Corrections: {corrections}")
                    total_corrections_extracted += len(corrections)
                    extracted_any = True

                if extracted_any:
                    # Process and save (handles deduplication and semantic link generation)
                    memory_extractor.process_extracted_entities(session_id, entities, interaction_id)
            
            # Record progress in tracker file
            with open(processed_file, "a", encoding="utf-8") as f:
                f.write(f"{interaction_id}\n")
                
            processed_count += 1
        except Exception as e:
            print(f"  Error processing interaction {interaction_id}: {e}")

    # Commit changes
    conn.commit()

    # Load goals/projects counts after starting
    cursor.execute("SELECT COUNT(*) FROM goals")
    goals_after = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM projects")
    projects_after = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM preferences")
    preferences_after = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM corrections")
    corrections_after = cursor.fetchone()[0]

    conn.close()

    print("\n==================================================")
    print("   EXTRACTION COMPLETED SUCCESSFULLY")
    print("==================================================")
    print(f"Total processed in this run: {processed_count}/{len(to_process)}")
    print(f"Goals: {goals_before} -> {goals_after} (+{goals_after - goals_before} new saved/mention updated)")
    print(f"Projects: {projects_before} -> {projects_after} (+{projects_after - projects_before} new saved/mention updated)")
    print(f"Preferences: {preferences_before} -> {preferences_after} (+{preferences_after - preferences_before} new saved/mention updated)")
    print(f"Corrections: {corrections_before} -> {corrections_after} (+{corrections_after - corrections_before} new saved/mention updated)")

    print("\nRebuilding similarity links & regenerating graph...")
    # Standalone script to clean and rebuild semantic similarity links
    # Run the Stages 1.5 & 2 from migrate_history.py to ensure the new entities have links
    import migrate_history
    migrate_history.migrate()

    # Export graph
    graph_visualizer.export_graph_to_html("memory_graph.html")
    print("Done! Interactive dashboard regenerated: memory_graph.html")

if __name__ == "__main__":
    run_extraction()
