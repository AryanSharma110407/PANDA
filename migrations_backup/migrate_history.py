"""
✨ PANDA — Retroactive Memory Migration Script
==============================================
Stage 1: Upgrade raw `conversations` (pre-Sprint 1) to semantic `interactions`.
Stage 1.5: Regenerate/Backfill vector embeddings for all entities.
Stage 2: Recalculate top-3 semantic links (edges) for all memory nodes.
"""

import sqlite3
import os
import sys

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_manager
import vector_memory

def migrate():
    print("==================================================")
    print("   PANDA MEMORY SYSTEM RETROACTIVE MIGRATION")
    print("==================================================")
    
    db_path = memory_manager.DB_PATH
    print(f"Database target: {db_path}")
    if not os.path.exists(db_path):
        print("Error: Database file does not exist!")
        return

    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    
    # -------------------------------------------------------------------------
    # STAGE 1: Migrate raw conversations to semantic interactions
    # -------------------------------------------------------------------------
    print("\n--- STAGE 1: Migrating raw conversations to semantic interactions ---")
    
    cursor.execute("SELECT * FROM conversations ORDER BY id ASC")
    all_msgs = [dict(row) for row in cursor.fetchall()]
    print(f"Loaded {len(all_msgs)} messages from 'conversations'.")
    
    # Group messages by session_id
    sessions = {}
    for msg in all_msgs:
        sessions.setdefault(msg["session_id"], []).append(msg)
    print(f"Found {len(sessions)} distinct conversation sessions.")
    
    migrated_count = 0
    skipped_count = 0
    low_importance_count = 0
    
    for session_id, msgs in sessions.items():
        # Get existing interactions for this session to prevent duplicates
        cursor.execute("SELECT user_message, assistant_response FROM interactions WHERE session_id = ?", (session_id,))
        existing_turns = {(row["user_message"].strip(), row["assistant_response"].strip()) for row in cursor.fetchall()}
        
        # Group messages in this session into conversational turns
        turns = []
        i = 0
        n = len(msgs)
        while i < n:
            msg = msgs[i]
            if msg["role"] == "user":
                j = i + 1
                user_texts = [msg["content"]]
                while j < n and msgs[j]["role"] == "user":
                    user_texts.append(msgs[j]["content"])
                    j += 1
                
                assistant_texts = []
                while j < n and msgs[j]["role"] == "assistant":
                    assistant_texts.append(msgs[j]["content"])
                    j += 1
                
                if assistant_texts:
                    turns.append({
                        "user_message": "\n".join(user_texts),
                        "assistant_response": "\n".join(assistant_texts),
                        "timestamp": msg["timestamp"]
                    })
                i = j
            else:
                i += 1
                
        # Migrate new turns
        for turn in turns:
            u_msg = turn["user_message"]
            a_resp = turn["assistant_response"]
            t_stamp = turn["timestamp"]
            
            # Deduplication
            if (u_msg.strip(), a_resp.strip()) in existing_turns:
                skipped_count += 1
                continue
                
            # Calculate importance score
            importance = vector_memory.calculate_importance(u_msg, a_resp)
            if importance < 0.20:
                low_importance_count += 1
                continue
                
            # Insert into interactions with the original timestamp
            cursor.execute("""
                INSERT INTO interactions (session_id, user_message, assistant_response, importance_score, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, u_msg, a_resp, importance, t_stamp))
            
            # Avoid duplicate insertion in same run
            existing_turns.add((u_msg.strip(), a_resp.strip()))
            migrated_count += 1
            
    conn.commit()
    print(f"Stage 1 completed:")
    print(f"  - Migrated {migrated_count} new interaction turns.")
    print(f"  - Skipped {skipped_count} duplicate turns.")
    print(f"  - Filtered out {low_importance_count} low-importance turns (score < 0.20).")
    
    # -------------------------------------------------------------------------
    # STAGE 1.5: Embeddings Backfill (Self-healing layer)
    # -------------------------------------------------------------------------
    print("\n--- STAGE 1.5: Backfilling missing vector embeddings ---")
    
    # Warmup the SentenceTransformer model
    print("Loading local embedding model...")
    vector_memory.get_embedding("warmup")
    
    # Find existing embeddings in vector_memory
    cursor.execute("SELECT source_table, source_id FROM vector_memory")
    existing_embs = {(row["source_table"], row["source_id"]) for row in cursor.fetchall()}
    print(f"Currently, there are {len(existing_embs)} embeddings in 'vector_memory'.")
    
    tables = ["interactions", "goals", "projects", "preferences", "corrections"]
    backfilled_count = 0
    
    for table in tables:
        cursor.execute(f"SELECT * FROM {table}")
        rows = [dict(row) for row in cursor.fetchall()]
        print(f"Checking '{table}' table ({len(rows)} total records)...")
        
        for row in rows:
            row_id = row["id"]
            if (table, row_id) in existing_embs:
                continue
                
            # Format text content matching the entity type
            if table == "interactions":
                content_text = row["user_message"]
            elif table == "goals":
                content_text = row["goal_text"]
            elif table == "projects":
                content_text = f"Project {row['project_name']}: {row['description']}"
            elif table == "preferences":
                content_text = row["preference_text"]
            elif table == "corrections":
                content_text = f"Correction: Previously thought '{row['mistake_context']}', but the truth is '{row['corrected_fact']}'"
            else:
                continue
                
            # Compute and save embedding
            emb = vector_memory.get_embedding(content_text)
            if emb is not None:
                memory_manager.save_embedding(table, row_id, content_text, emb)
                backfilled_count += 1
                if backfilled_count % 20 == 0:
                    print(f"  Generated {backfilled_count} embeddings...")
                    
    print(f"Stage 1.5 completed: Backfilled {backfilled_count} missing embeddings.")
    
    # -------------------------------------------------------------------------
    # STAGE 2: Recalculate and backfill entity links (edges)
    # -------------------------------------------------------------------------
    print("\n--- STAGE 2: Recalculating and backfilling semantic similarity links ---")
    
    # Clear existing similarity links to compute from scratch
    cursor.execute("DELETE FROM entity_links WHERE link_type = 'semantic_similarity'")
    conn.commit()
    print("Cleared existing 'semantic_similarity' links.")
    
    # Load all memories enriched with embeddings
    memories = memory_manager.load_all_memories_with_embeddings()
    print(f"Loaded {len(memories)} total memories with embeddings for matching.")
    
    links_created = 0
    for idx, memory in enumerate(memories):
        table = memory["source_table"]
        row_id = memory["source_id"]
        content_text = memory["content_text"]
        
        # Cache top-3 closest semantic neighbors
        vector_memory._cache_top_semantic_links(table, row_id, content_text, top_k=3)
        links_created += 1
        if links_created % 20 == 0:
            print(f"  Calculated similarity edges for {links_created}/{len(memories)} entities...")
            
    cursor.execute("SELECT COUNT(*) FROM entity_links")
    total_edges = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\nStage 2 completed: Entity edges backfilled. Total edges in database: {total_edges}")
    print("\n==================================================")
    print("   MEMORY MIGRATION COMPLETED SUCCESSFULLY")
    print("==================================================")

if __name__ == "__main__":
    migrate()
