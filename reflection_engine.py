"""
✨ PANDA — Episodic Memory & Reflection Engine (Sprint 5)
=========================================================
Adds active cognitive processing to PANDA's SQLite memory.

Features:
1. Session Summarization: Generates conversational summaries and indexes them in vector memory.
2. Routine/Pattern Reflections: Analyzes past summaries to find routine patterns and saves them as insights.
3. Cautious Memory Consolidation: Merges highly similar goals/preferences and links old ones to the new merged ID.
4. Learning from Mistakes: Converts user corrections into actionable "rules of thumb" reflections.
5. Differentiated Synapse Decay: Decays memory tables at customized rates (fast for interactions, slow for goals, never for corrections).
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

# Differentiated decay rates per table (percent decrease per day)
DECAY_RATES = {
    "interactions": 0.035,  # Fast decay (3.5% per day)
    "projects": 0.015,      # Medium decay (1.5% per day)
    "goals": 0.005,         # Very slow decay (0.5% per day)
    "preferences": 0.005,   # Very slow decay (0.5% per day)
    "reflections": 0.010,   # Slow decay (1.0% per day)
    "corrections": 0.000    # Never decay (0% decay - hold permanent corrections)
}

def _get_ollama_client() -> ollama.Client:
    return ollama.Client(host=OLLAMA_URL, timeout=120.0, headers={"ngrok-skip-browser-warning": "true"})


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 1: SESSION SUMMARIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def summarize_session(session_id: str) -> str | None:
    """
    Summarizes all turns of a conversation session, extracts key takeaways,
    saves it in the database, and indexes it in vector memory.
    """
    print(f"  [ReflectionEngine] Summarizing session '{session_id}'...")
    
    # Load session messages
    messages = memory_manager.load_session_messages(session_id, limit=9999)
    if not messages:
        print("  [ReflectionEngine] No messages found for session summary.")
        return None
        
    # Format messages as transcript
    transcript_lines = []
    for msg in messages:
        role_label = "Aryan (User)" if msg["role"] == "user" else "PANDA (Assistant)"
        transcript_lines.append(f"{role_label}: {msg['content']}")
    transcript = "\n".join(transcript_lines)
    
    prompt = (
        "You are PANDA's memory processor. Analyze the conversation transcript.\n"
        "1. Summarize what was discussed/achieved (max 3 sentences).\n"
        "2. Extract a JSON list of key takeaways, facts learned, or decisions.\n\n"
        f"Transcript:\n{transcript}\n\n"
        "Output format: Reply with ONLY a JSON object containing 'summary' (string) and 'key_takeaways' (list of strings). No markdown or explanation."
    )
    
    try:
        client = _get_ollama_client()
        response = client.chat(
            model=MODEL_NAME,
            format="json",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 256}
        )
        
        raw = response["message"]["content"].strip()
        data = json.loads(raw)
        
        summary_text = data.get("summary", "").strip()
        key_takeaways = data.get("key_takeaways", [])
        
        if not summary_text:
            print("  [ReflectionEngine] LLM returned empty summary.")
            return None
            
        # Save to database
        summary_id = memory_manager.save_session_summary(session_id, summary_text, key_takeaways)
        print(f"  [ReflectionEngine] Saved session summary to DB (ID: {summary_id}).")
        
        # Embed and index in vector memory
        emb = vector_memory.get_embedding(summary_text)
        if emb is not None:
            memory_manager.save_embedding(
                source_table="session_summaries",
                source_id=summary_id,
                content_text=summary_text,
                embedding=emb
            )
            # Pre-warm vector cache
            vector_memory._entity_embedding_cache[("session_summaries", summary_id)] = emb
            vector_memory._cache_top_semantic_links("session_summaries", summary_id, summary_text, top_k=3)
            print(f"  [ReflectionEngine] Embedded and indexed session summary in vector space.")
            
        return summary_text
        
    except Exception as e:
        print(f"  [ReflectionEngine] Session summarization failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 2: DAILY/WEEKLY REFLECTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_reflections(reflection_type: str = "daily") -> list:
    """
    Gathers recent session summaries (past 10 summaries) and interactions,
    analyzes patterns/routines using Ollama, and saves new insights as reflections.
    """
    print(f"  [ReflectionEngine] Generating {reflection_type} reflections...")
    
    # Load recent session summaries
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM session_summaries ORDER BY created_at DESC LIMIT 10")
    summaries = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    if not summaries:
        print("  [ReflectionEngine] No session summaries available to reflect on.")
        return []
        
    # Format summaries for the prompt
    summaries_text_lines = []
    for idx, s in enumerate(summaries, 1):
        try:
            takeaways = json.loads(s["key_takeaways"])
            takeaways_str = ", ".join([f"'{t}'" for t in takeaways])
        except Exception:
            takeaways_str = "None"
        summaries_text_lines.append(f"Session {idx} ({s['created_at'].split('T')[0]}):\n- Summary: {s['summary_text']}\n- Takeaways: {takeaways_str}")
    summaries_context = "\n\n".join(summaries_text_lines)
    
    prompt = (
        "You are PANDA's reflection engine. Analyze these recent session summaries.\n"
        "Identify Aryan's recurring routines, interests, preferences, projects, or goals.\n\n"
        f"History:\n{summaries_context}\n\n"
        "Output format: Reply with ONLY a JSON object containing a 'reflections' list of objects. Each object must have:\n"
        "- 'insight': Pattern/insight statement (max 1 sentence)\n"
        "- 'category': 'routine', 'preference', 'project', or 'learning'\n"
        "- 'importance': Importance score from 0.0 to 1.0\n"
        "No markdown or explanations."
    )
    
    new_reflections = []
    try:
        client = _get_ollama_client()
        response = client.chat(
            model=MODEL_NAME,
            format="json",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2, "num_predict": 512}
        )
        
        raw = response["message"]["content"].strip()
        data = json.loads(raw)
        reflections_list = data.get("reflections", [])
        
        for r in reflections_list:
            insight = r.get("insight", "").strip()
            category = r.get("category", "routine").strip()
            importance = float(r.get("importance", 0.5))
            
            if not insight:
                continue
                
            # Deduplicate reflections
            existing_reflections = memory_manager.load_reflections(reflection_type)
            is_dup = False
            for exist in existing_reflections:
                if exist["insight_text"].lower().strip() == insight.lower().strip():
                    is_dup = True
                    # If duplicate, just boost the importance slightly (Automatic Promotion)
                    memory_manager.boost_memory_importance("reflections", exist["id"], 0.10)
                    print(f"  [ReflectionEngine] Duplicate reflection detected: '{insight}'. Boosted importance.")
                    break
                    
            if not is_dup:
                ref_id = memory_manager.save_reflection(
                    reflection_type=reflection_type,
                    insight_text=insight,
                    category=category,
                    importance_score=importance
                )
                print(f"  [ReflectionEngine] Created new reflection (ID: {ref_id}): '{insight}'")
                
                # Embed and index
                emb = vector_memory.get_embedding(insight)
                if emb is not None:
                    memory_manager.save_embedding(
                        source_table="reflections",
                        source_id=ref_id,
                        content_text=insight,
                        embedding=emb
                    )
                    vector_memory._entity_embedding_cache[("reflections", ref_id)] = emb
                    vector_memory._cache_top_semantic_links("reflections", ref_id, insight, top_k=3)
                    
                new_reflections.append(insight)
                
        # Trigger graph visualizer export so new reflections show up
        vector_memory._trigger_graph_export()
        return new_reflections
        
    except Exception as e:
        print(f"  [ReflectionEngine] Reflection generation failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 3: CAUTIOUS MEMORY CONSOLIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def consolidate_memories() -> int:
    """
    Finds pairs of highly similar active goals or preferences (cosine similarity >= 0.80),
    prompts the LLM to merge them, creates a new merged entry, and updates original entries
    with a consolidated_to reference. This soft-archives old duplicates, preserving history.
    """
    print("  [ReflectionEngine] Consolidating memory entities...")
    consolidated_count = 0
    
    # We consolidate goals and preferences separately
    entity_types = ["goals", "preferences"]
    
    for etype in entity_types:
        # Load all active, unconsolidated entities
        conn = memory_manager._get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {etype} WHERE consolidated_to IS NULL AND importance_score >= 0.10")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        if len(rows) < 2:
            continue
            
        # Compute embeddings and find similar pairs
        pairs_to_merge = []
        checked_pairs = set()
        
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                id_a, id_b = rows[i]["id"], rows[j]["id"]
                pair_key = tuple(sorted((id_a, id_b)))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                text_a = rows[i]["goal_text"] if etype == "goals" else rows[i]["preference_text"]
                text_b = rows[j]["goal_text"] if etype == "goals" else rows[j]["preference_text"]
                
                emb_a = vector_memory._get_cached_embedding(etype[:-1], id_a, text_a)
                emb_b = vector_memory._get_cached_embedding(etype[:-1], id_b, text_b)
                
                if emb_a and emb_b:
                    sim = vector_memory.cosine_similarity(emb_a, emb_b)
                    if sim >= 0.80:
                        # Add to merge candidates
                        pairs_to_merge.append((rows[i], rows[j], sim))
                        
        # Merge identified pairs cautiously
        for entity_a, entity_b, sim in pairs_to_merge:
            # Check if either has already been consolidated in this batch
            conn = memory_manager._get_connection()
            cursor = conn.cursor()
            cursor.execute(f"SELECT consolidated_to FROM {etype} WHERE id IN (?, ?)", (entity_a["id"], entity_b["id"]))
            already_merged = any(row["consolidated_to"] is not None for row in cursor.fetchall())
            conn.close()
            
            if already_merged:
                continue
                
            text_a = entity_a["goal_text"] if etype == "goals" else entity_a["preference_text"]
            text_b = entity_b["goal_text"] if etype == "goals" else entity_b["preference_text"]
            
            print(f"  [ReflectionEngine] Consolidating similar {etype} ({sim:.2f} sim):\n    1. '{text_a}'\n    2. '{text_b}'")
            
            prompt = (
                f"You are PANDA's memory consolidation core. Merge these similar user {etype[:-1]} records, preserving specific facts.\n\n"
                f"1. {text_a}\n"
                f"2. {text_b}\n\n"
                f"Output format: Output ONLY the merged statement. No markdown or conversational intros."
            )
            
            try:
                client = _get_ollama_client()
                response = client.chat(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.2, "num_predict": 128}
                )
                
                merged_text = response["message"]["content"].strip()
                if merged_text and merged_text not in (text_a, text_b):
                    # Save the new consolidated memory
                    session_id = entity_a["session_id"]
                    new_importance = max(entity_a["importance_score"], entity_b["importance_score"])
                    new_mentions = entity_a["mention_count"] + entity_b["mention_count"]
                    
                    if etype == "goals":
                        new_id = vector_memory.save_goal_semantic(
                            session_id=session_id,
                            goal_text=merged_text,
                            status="active",
                            extracted_from=entity_a["extracted_from_interaction_id"],
                            confidence=0.85
                        )
                    else:
                        new_id = vector_memory.save_preference_semantic(
                            session_id=session_id,
                            preference_text=merged_text,
                            extracted_from=entity_a["extracted_from_interaction_id"],
                            confidence=0.85
                        )
                        
                    # Set mention count and importance score
                    conn = memory_manager._get_connection()
                    cursor = conn.cursor()
                    cursor.execute(f"""
                        UPDATE {etype} 
                        SET importance_score = ?, mention_count = ?
                        WHERE id = ?
                    """, (new_importance, new_mentions, new_id))
                    
                    # Cautious soft-archiving: link original records to the new consolidated ID
                    cursor.execute(f"""
                        UPDATE {etype}
                        SET consolidated_to = ?
                        WHERE id IN (?, ?)
                    """, (new_id, entity_a["id"], entity_b["id"]))
                    
                    # Keep RAG edges updated: link consolidate_to node
                    cursor.execute("""
                        DELETE FROM entity_links 
                        WHERE (source_table = ? AND source_id IN (?, ?))
                           OR (target_table = ? AND target_id IN (?, ?))
                    """, (etype, entity_a["id"], entity_b["id"], etype, entity_a["id"], entity_b["id"]))
                    
                    conn.commit()
                    conn.close()
                    
                    print(f"  [ReflectionEngine] Successfully consolidated into new entity (ID: {new_id}): '{merged_text}'")
                    consolidated_count += 1
            except Exception as merge_err:
                print(f"  [ReflectionEngine] Cautious consolidation failed for pair: {merge_err}")
                
    if consolidated_count > 0:
        vector_memory._trigger_graph_export()
        
    return consolidated_count


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 4: LEARNING FROM MISTAKES
# ═══════════════════════════════════════════════════════════════════════════════

def learn_from_mistakes() -> int:
    """
    Scans the corrections table for recent corrected mistakes.
    Generates generalized "rules of thumb" or generalized rules of action,
    storing them as reflections to prevent repeating mistakes.
    """
    print("  [ReflectionEngine] Reviewing corrections to learn from mistakes...")
    
    # Load recent corrections (e.g. from the past 7 days)
    corrections = memory_manager.load_corrections()
    if not corrections:
        print("  [ReflectionEngine] No corrections found to learn from.")
        return 0
        
    # Filter to only look at corrections with high importance that haven't faded
    active_corrs = [c for c in corrections if c["importance_score"] >= 0.3]
    if not active_corrs:
        return 0
        
    formatted_corrs = []
    for idx, c in enumerate(active_corrs, 1):
        formatted_corrs.append(f"Mistake {idx}: assistant believed '{c['mistake_context']}' -> user corrected to '{c['corrected_fact']}'")
    corrections_list_str = "\n".join(formatted_corrs)
    
    prompt = (
        "You are PANDA's self-correction system. Analyze user corrections of PANDA's mistakes.\n"
        "Extract general, actionable rules of thumb PANDA must follow to prevent repeating them.\n\n"
        f"Mistakes:\n{corrections_list_str}\n\n"
        "Output format: Reply with ONLY a JSON object containing a 'rules' list of strings. No markdown or explanations."
    )
    
    rules_count = 0
    try:
        client = _get_ollama_client()
        response = client.chat(
            model=MODEL_NAME,
            format="json",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 256}
        )
        
        raw = response["message"]["content"].strip()
        data = json.loads(raw)
        rules = data.get("rules", [])
        
        for rule in rules:
            rule = rule.strip()
            if not rule:
                continue
                
            # Save rule as a high-importance reflection of category 'correction'
            reflections = memory_manager.load_reflections()
            is_dup = any(ref["insight_text"].lower().strip() == rule.lower().strip() for ref in reflections)
            
            if not is_dup:
                ref_id = memory_manager.save_reflection(
                    reflection_type="daily",
                    insight_text=rule,
                    category="correction",
                    importance_score=0.95 # High initial importance since it's a correction rule
                )
                print(f"  [ReflectionEngine] Learned new rule to avoid mistakes (ID: {ref_id}): '{rule}'")
                
                # Embed and index
                emb = vector_memory.get_embedding(rule)
                if emb is not None:
                    memory_manager.save_embedding(
                        source_table="reflections",
                        source_id=ref_id,
                        content_text=rule,
                        embedding=emb
                    )
                    vector_memory._entity_embedding_cache[("reflections", ref_id)] = emb
                    vector_memory._cache_top_semantic_links("reflections", ref_id, rule, top_k=3)
                    
                rules_count += 1
                
        if rules_count > 0:
            vector_memory._trigger_graph_export()
            
        return rules_count
        
    except Exception as e:
        print(f"  [ReflectionEngine] Learning from mistakes failed: {e}")
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 5: SYNAPSE IMPORTANCE DECAY
# ═══════════════════════════════════════════════════════════════════════════════

def apply_memory_decay() -> int:
    """
    Decays the importance_score of all inactive memories based on age.
    Differentiated decay rates are applied (interactions decay fast, goals very slow, corrections never).
    Returns the count of memory records decayed.
    """
    print("  [ReflectionEngine] Applying memory decay calculations...")
    decayed_count = 0
    now = datetime.datetime.now()
    
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    
    # We process each table individually using its specific decay rate
    for table_name, rate in DECAY_RATES.items():
        if rate == 0.0:
            # Skip tables with 0% decay (e.g. corrections)
            continue
            
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = [dict(row) for row in cursor.fetchall()]
        
        for row in rows:
            row_id = row["id"]
            orig_score = row["importance_score"]
            
            # Determine last activity time
            time_str = row.get("updated_at") or row.get("timestamp") or row.get("created_at")
            if not time_str:
                continue
                
            try:
                # Handle possible milliseconds / ISO string
                time_str_parsed = time_str.split(".")[0]
                if "T" in time_str_parsed:
                    dt = datetime.datetime.strptime(time_str_parsed, "%Y-%m-%dT%H:%M:%S")
                else:
                    dt = datetime.datetime.strptime(time_str_parsed, "%Y-%m-%d %H:%M:%S")
            except Exception:
                # Default to current date if parsing fails so we don't crash
                dt = now
                
            days_past = (now - dt).days
            if days_past <= 0:
                continue
                
            # Calculate decayed score: score * (1 - rate)^days
            decayed_score = orig_score * ((1 - rate) ** days_past)
            decayed_score = round(max(0.0, decayed_score), 4)
            
            if decayed_score != orig_score:
                # Save the new decayed score without updating the updated_at timestamp
                # (so that we don't reset the decay timer!)
                if table_name == "interactions":
                    cursor.execute("UPDATE interactions SET importance_score = ? WHERE id = ?", (decayed_score, row_id))
                elif table_name == "reflections":
                    cursor.execute("UPDATE reflections SET importance_score = ? WHERE id = ?", (decayed_score, row_id))
                else:
                    cursor.execute(f"UPDATE {table_name} SET importance_score = ? WHERE id = ?", (decayed_score, row_id))
                
                decayed_count += 1
                
    conn.commit()
    conn.close()
    
    print(f"  [ReflectionEngine] Memory decay calculations complete. Decayed {decayed_count} memory synapses.")
    
    # Trigger export to visualize decayed nodes (they will shrink in size!)
    if decayed_count > 0:
        vector_memory._trigger_graph_export()
        
    return decayed_count


# ═══════════════════════════════════════════════════════════════════════════════
# CONSOLIDATED RUNNER (BACKGROUND DAEMON ROUTINE)
# ═══════════════════════════════════════════════════════════════════════════════

def run_reflection_pipeline(session_id: str):
    """
    Runs the full cognitive pipeline in a non-blocking sequence.
    Typically called in a background thread on shutdown.
    """
    try:
        # 1. Summarize current session
        summarize_session(session_id)
        
        # 2. Reflect on routines & patterns
        generate_reflections("daily")
        
        # 3. Learn from mistakes
        learn_from_mistakes()
        
        # 4. Consolidate redundant goals/preferences
        consolidate_memories()
        
        # 5. Apply differentiated memory decay
        apply_memory_decay()
        
        # 6. Process goals progress and reflections
        process_goals_reflection()
        
        print("  [ReflectionEngine] Background memory reflection sequence completed successfully.")
    except Exception as e:
        print(f"  [ReflectionEngine] Background memory reflection failed: {e}")


def process_goals_reflection():
    """
    Called on session exit to process goal velocity updates, auto-complete detection,
    and save reflections for stale/completed goals.
    """
    print("  [ReflectionEngine] Processing goals reflections and plans...")
    import memory_manager
    import goal_engine
    
    # Load all active, non-consolidated goals
    goals = memory_manager.load_goals(status='active')
    
    for goal in goals:
        goal_id = goal["id"]
        goal_text = goal["goal_text"]
        
        # 1. Update completion velocity
        goal_engine.update_completion_velocity(goal_id)
        
        # Reload goal to get latest progress
        conn = memory_manager._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        goal_latest = dict(cursor.fetchone())
        conn.close()
        
        progress = goal_latest.get("progress_pct", 0.0)
        current_ver = goal_latest.get("current_plan_version", 0)
        
        # 2. Check if goal is 100% complete
        if current_ver > 0 and progress >= 1.0:
            memory_manager.update_goal_status(goal_id, "completed")
            
            # Count steps
            steps = memory_manager.load_goal_steps(goal_id)
            step_count = len(steps)
            insight_text = f"Aryan completed goal: '{goal_text}' after planning {step_count} steps and finishing all of them."
            memory_manager.save_reflection(
                reflection_type="insight",
                insight_text=insight_text,
                category="goals",
                importance_score=0.90
            )
            print(f"  [ReflectionEngine] Goal completed & reflection saved: '{goal_text}'")
            continue
            
        # 3. Check for stale goal (14+ days of no progress)
        updated_at_str = goal_latest.get("updated_at")
        if updated_at_str:
            try:
                updated_at = datetime.datetime.fromisoformat(updated_at_str)
                delta_days = (datetime.datetime.now() - updated_at).days
                if delta_days >= 14 and goal_latest.get("status") == "active":
                    insight_text = f"Goal '{goal_text}' has had no progress in {delta_days} days. Consider pausing or replanning it."
                    
                    # Prevent duplicate stale reminders
                    reflections = memory_manager.load_reflections(reflection_type="nudge")
                    duplicate = any(insight_text in r["insight_text"] for r in reflections)
                    if not duplicate:
                        memory_manager.save_reflection(
                            reflection_type="nudge",
                            insight_text=insight_text,
                            category="goals",
                            importance_score=0.40
                        )
                        print(f"  [ReflectionEngine] Saved stale nudge reflection for: '{goal_text}'")
            except Exception as e:
                print(f"  [ReflectionEngine] Error checking stale goal: {e}")
