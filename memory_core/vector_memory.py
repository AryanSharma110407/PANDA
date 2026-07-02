"""
✨ PANDA — Vector Memory & RAG Core
======================================
Manages semantic indexing, heuristic importance, and vector similarity search.
Uses the project's existing SentenceTransformer model locally.
"""

import sys
import os
import threading
import time


# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_core.memory_manager as memory_manager


def get_embedding(text: str):
    """
    Generates a 384-dimensional vector embedding of the input text.
    Reuses the lazy-loaded model from smart_brain to avoid redundant memory usage and lag.
    Returns a list of floats, or None on failure.
    """
    try:
        import smart_brain
        model = smart_brain._get_embedding_model()
        embedding = model.encode(text)
        return embedding.tolist()
    except Exception as e:
        print(f"  [VectorMemory] Error generating embedding: {e}")
        return None


def calculate_importance(user_message: str, assistant_response: str) -> float:
    """
    Computes a cognitive importance score (0.05 to 0.95) based on the interaction.
    - 0.95: Major life goals / career ambitions
    - 0.75: Active projects or specific tools/languages
    - 0.30: General conversation or informational queries
    - 0.05: Greetings, casual acknowledgments, or exit commands
    """
    user_lower = user_message.lower().strip("?,!.")
    combined_lower = (user_message + " " + assistant_response).lower()

    # High importance indicators (Goals)
    goal_keywords = ["ceo", "microsoft", "career", "become", "goal", "ambition", "dream", "job", "future"]
    if any(kw in combined_lower for kw in goal_keywords):
        return 0.95

    # Projects (Alya, database design, voice assistant details)
    project_keywords = ["project", "alya", "voice system", "database", "repository"]
    if any(kw in combined_lower for kw in project_keywords):
        return 0.75

    # Greetings / exit / short casual responses (e.g. "hello there panda")
    low_keywords = {
        "hello", "hi", "hey", "sup", "yo", "thanks", "thank you", "okay", "ok", 
        "yep", "yes", "no", "bye", "goodbye", "quit", "exit", "there", "panda"
    }
    user_words = [w.strip("?,!.") for w in user_lower.split()]
    if len(user_words) <= 3 and all(w in low_keywords or len(w) <= 3 for w in user_words):
        return 0.05

    return 0.30


def cosine_similarity(v1: list, v2: list) -> float:
    """Computes cosine similarity between two float vectors."""
    dot_prod = sum(a * b for a, b in zip(v1, v2))
    mag1 = sum(a * a for a in v1) ** 0.5
    mag2 = sum(b * b for b in v2) ** 0.5
    if not mag1 or not mag2:
        return 0.0
    return dot_prod / (mag1 * mag2)


def semantic_search(query_text: str, top_k: int = 3) -> list:
    """
    Searches stored interactions, goals, projects, preferences, and corrections using semantic similarity.
    Scores are adjusted based on entity type and importance_score:
      Final Priority = Similarity * Entity Weight * Importance Score
      Weights: corrections=1.5, goals=1.3, projects=1.1, interactions/default=1.0, preferences=0.9.
    Returns: List of matching records with mapped keys (so smart_brain doesn't break).
    """
    query_emb = get_embedding(query_text)
    if query_emb is None:
        return []

    # Load all memories with their embeddings
    memories = memory_manager.load_all_memories_with_embeddings()
    if not memories:
        return []

    entity_weights = {
        "corrections": 1.5,
        "reflections": 1.4,
        "goals": 1.3,
        "projects": 1.1,
        "session_summaries": 1.0,
        "interactions": 1.0,
        "preferences": 0.9
    }

    scored_memories = []
    for memory in memories:
        importance = memory["importance_score"]

        sim = cosine_similarity(query_emb, memory["embedding"])
        
        # We only consider memories with a positive semantic relation (threshold > 0.30)
        if sim < 0.30:
            continue
            
        weight = entity_weights.get(memory["source_table"], 1.0)
        priority_score = sim * weight * importance
        
        # Map to user_message / assistant_response so smart_brain RAG hook doesn't break
        if memory["source_table"] == "goals":
            user_msg = f"Active Goal: {memory['content_text']}"
            asst_resp = f"Status: {memory.get('goal_status', 'active')}"
        elif memory["source_table"] == "projects":
            user_msg = f"Active Project: {memory['content_text']}"
            asst_resp = "Project active."
        elif memory["source_table"] == "preferences":
            user_msg = f"User Preference: {memory['content_text']}"
            asst_resp = "Preference recorded."
        elif memory["source_table"] == "corrections":
            user_msg = memory['content_text']
            asst_resp = "Correction applied."
        elif memory["source_table"] == "reflections":
            user_msg = f"Insight / Reflection: {memory['content_text']}"
            asst_resp = "Pattern recognized."
        elif memory["source_table"] == "session_summaries":
            user_msg = f"Past Session Summary: {memory['content_text']}"
            asst_resp = "Episode remembered."
        else:
            user_msg = memory["content_text"]
            asst_resp = memory.get("assistant_response") or "Acknowledged."

        scored_memories.append({
            "id": memory["id"],
            "source_table": memory["source_table"],
            "source_id": memory["source_id"],
            "session_id": memory["session_id"],
            "user_message": user_msg,
            "assistant_response": asst_resp,
            "importance_score": importance,
            "timestamp": memory["timestamp"],
            "similarity": round(sim, 4),
            "score": round(priority_score, 4)
        })

    # Sort by priority score descending
    scored_memories.sort(key=lambda x: x["score"], reverse=True)
    return scored_memories[:top_k]

def _cache_top_semantic_links(source_table: str, source_id: int, query_text: str, top_k: int = 3):
    """
    Finds the top-K semantically related memories and caches them as edges in the entity_links table.
    """
    matches = semantic_search(query_text, top_k=top_k + 1) # fetch +1 in case we match ourselves
    
    links_created = 0
    for match in matches:
        if links_created >= top_k:
            break
            
        # Don't link to itself
        if match["source_table"] == source_table and match["source_id"] == source_id:
            continue
            
        memory_manager.save_entity_link(
            source_table=source_table,
            source_id=source_id,
            target_table=match["source_table"],
            target_id=match["source_id"],
            similarity_score=match["similarity"],
            link_type='semantic_similarity'
        )
        links_created += 1

# ═══════════════════════════════════════════════════════════════════════════════
# EMBEDDING CACHE — avoids re-embedding goals/projects on every turn
# ═══════════════════════════════════════════════════════════════════════════════
# Key: ("goal", goal_id) or ("project", proj_id) → embedding list
# Invalidated when new entities are added via invalidate_entity_cache()
_entity_embedding_cache: dict[tuple, list] = {}


def _get_cached_embedding(entity_type: str, entity_id: int, text: str) -> list | None:
    """
    Returns the embedding for an entity, using the cache if available.
    On cache miss, embeds the text and stores the result for future use.
    """
    cache_key = (entity_type, entity_id)
    if cache_key in _entity_embedding_cache:
        return _entity_embedding_cache[cache_key]

    emb = get_embedding(text)
    if emb is not None:
        _entity_embedding_cache[cache_key] = emb
    return emb


def invalidate_entity_cache(entity_type: str = None, entity_id: int = None):
    """
    Clears cached embeddings. Call when entities are added or modified.
    If both entity_type and entity_id are given, clears only that entry.
    If only entity_type is given, clears all entries of that type.
    If neither is given, clears the entire cache.
    """
    if entity_type and entity_id:
        _entity_embedding_cache.pop((entity_type, entity_id), None)
    elif entity_type:
        keys_to_remove = [k for k in _entity_embedding_cache if k[0] == entity_type]
        for k in keys_to_remove:
            del _entity_embedding_cache[k]
    else:
        _entity_embedding_cache.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# MENTION COOLDOWN — prevents inflating mention_count in one session
# ═══════════════════════════════════════════════════════════════════════════════
# Key: session_id → set of (entity_type, entity_id) already mentioned
# Each entity can only be counted ONCE per session, no matter how many times
# the topic comes up. Next session, the set is fresh.
_session_mention_tracker: dict[str, set[tuple]] = {}


def _has_been_mentioned_this_session(session_id: str, entity_type: str, entity_id: int) -> bool:
    """
    Returns True if this entity was already counted in this session.
    If not, marks it as counted and returns False.
    """
    key = (entity_type, entity_id)
    if session_id not in _session_mention_tracker:
        _session_mention_tracker[session_id] = set()

    if key in _session_mention_tracker[session_id]:
        return True  # Already counted this session — skip

    _session_mention_tracker[session_id].add(key)
    return False  # First time this session — allow increment


_last_graph_export_time = 0.0
_graph_export_lock = threading.Lock()

def _trigger_graph_export():
    """
    Triggers graph visualizer export to memory_graph.html in a background thread.
    Throttled to run at most once every 5 minutes (300 seconds).
    Catches all exceptions to ensure it never crashes caller workflows.
    """
    global _last_graph_export_time
    
    now = time.time()
    if now - _last_graph_export_time < 300:
        return
        
    def _bg_export():
        global _last_graph_export_time
        if not _graph_export_lock.acquire(blocking=False):
            return
        try:
            if time.time() - _last_graph_export_time < 300:
                return
            import graph_visualizer
            graph_visualizer.export_graph_to_html("memory_graph.html")
            _last_graph_export_time = time.time()
        except Exception as e:
            print(f"  [VectorMemory] Auto-update graph export failed: {e}")
        finally:
            _graph_export_lock.release()

    import threading
    threading.Thread(target=_bg_export, daemon=True).start()

def save_turn_semantic(session_id: str, user_message: str, assistant_response: str):
    """
    Calculates importance, saves the turn to interactions, and indexes it in vector_memory.
    Runs safely in a background thread — catches all exceptions to avoid silent crashes.
    Also dynamically checks active goals, projects, preferences, and corrections for matches to update their mention_count,
    using a cache to avoid re-embedding every entity on every single message.
    """
    try:
        # Calculate importance score
        importance = calculate_importance(user_message, assistant_response)

        # Save raw turn to interactions table
        interaction_id = memory_manager.save_interaction(
            session_id=session_id,
            user_message=user_message,
            assistant_response=assistant_response,
            importance_score=importance
        )

        # Embed the user message (as it holds the main query/intent)
        emb = get_embedding(user_message)
        if emb is None:
            # Don't pollute DB with zero vectors if embedding failed
            print("  [VectorMemory] Skipping embedding save — model unavailable.")
            return interaction_id

        memory_manager.save_embedding(
            source_table="interactions",
            source_id=interaction_id,
            content_text=user_message,
            embedding=emb
        )

        # Cache top 3 semantic relationships
        _cache_top_semantic_links("interactions", interaction_id, user_message, top_k=3)

        # Skip mention counting for low-importance interactions (greetings, casual chat)
        # This avoids wasting compute on "hello" or "thanks" messages
        if importance < 0.20:
            return interaction_id

        # Dynamic mention count check using cached embeddings:
        # Each entity can only be counted ONCE per session (cooldown).
        # Check against all active goals
        goals = memory_manager.load_goals(status='active')
        for goal in goals:
            goal_emb = _get_cached_embedding("goal", goal["id"], goal["goal_text"])
            if goal_emb:
                sim = cosine_similarity(emb, goal_emb)
                if sim > 0.70:
                    if not _has_been_mentioned_this_session(session_id, "goal", goal["id"]):
                        memory_manager.increment_goal_mention(goal["id"])
                        print(f"  [VectorMemory] Dynamically matched active goal '{goal['goal_text']}' (similarity: {sim:.2f}) — incremented mention count.")
                    else:
                        print(f"  [VectorMemory] Goal '{goal['goal_text']}' already counted this session — skipping.")

        # Check against all projects
        projects = memory_manager.load_projects()
        for proj in projects:
            proj_text = f"Project {proj['project_name']}: {proj['description']}"
            proj_emb = _get_cached_embedding("project", proj["id"], proj_text)
            if proj_emb:
                sim = cosine_similarity(emb, proj_emb)
                if sim > 0.70:
                    if not _has_been_mentioned_this_session(session_id, "project", proj["id"]):
                        memory_manager.increment_project_mention(proj["id"])
                        print(f"  [VectorMemory] Dynamically matched active project '{proj['project_name']}' (similarity: {sim:.2f}) — incremented mention count.")
                    else:
                        print(f"  [VectorMemory] Project '{proj['project_name']}' already counted this session — skipping.")

        # Check against all preferences
        preferences = memory_manager.load_preferences()
        for pref in preferences:
            pref_emb = _get_cached_embedding("preference", pref["id"], pref["preference_text"])
            if pref_emb:
                sim = cosine_similarity(emb, pref_emb)
                if sim > 0.70:
                    if not _has_been_mentioned_this_session(session_id, "preference", pref["id"]):
                        memory_manager.increment_preference_mention(pref["id"])
                        print(f"  [VectorMemory] Dynamically matched preference '{pref['preference_text']}' (similarity: {sim:.2f}) — incremented mention count.")
                    else:
                        print(f"  [VectorMemory] Preference '{pref['preference_text']}' already counted this session — skipping.")

        # Check against all corrections
        corrections = memory_manager.load_corrections()
        for corr in corrections:
            corr_text = f"Correction: Previously thought '{corr['mistake_context']}', but the truth is '{corr['corrected_fact']}'"
            corr_emb = _get_cached_embedding("correction", corr["id"], corr_text)
            if corr_emb:
                sim = cosine_similarity(emb, corr_emb)
                if sim > 0.70:
                    if not _has_been_mentioned_this_session(session_id, "correction", corr["id"]):
                        memory_manager.increment_correction_mention(corr["id"])
                        print(f"  [VectorMemory] Dynamically matched correction mistake '{corr['mistake_context']}' -> '{corr['corrected_fact']}' (similarity: {sim:.2f}) — incremented mention count.")
                    else:
                        print(f"  [VectorMemory] Correction '{corr['mistake_context']}' already counted this session — skipping.")

        # ── Memory Extraction Pipeline ────────────────────────────────────────
        # After mention counting, run the LLM extractor to auto-detect
        # goals/projects/preferences/corrections from organic conversation.
        # Runs in the SAME background thread — no extra latency for the user.
        try:
            import memory_extractor
            memory_extractor.extract_and_save(
                session_id=session_id,
                user_message=user_message,
                assistant_response=assistant_response,
                interaction_id=interaction_id
            )
        except Exception as extraction_err:
            # Non-fatal — extraction failure should never break the save pipeline
            print(f"  [VectorMemory] Memory extraction error (non-fatal): {extraction_err}")

        # Trigger auto-update of memory graph visualization
        _trigger_graph_export()

        return interaction_id
    except Exception as e:
        print(f"  [VectorMemory] Background save error: {e}")


def save_goal_semantic(session_id: str, goal_text: str, status: str = 'active', extracted_from: int = None, confidence: float = 1.0) -> int:
    """
    Calculates importance, saves the goal to goals table, and indexes it in vector_memory.
    """
    importance = calculate_importance(goal_text, "")
    goal_id = memory_manager.save_goal(
        session_id=session_id,
        goal_text=goal_text,
        status=status,
        importance_score=importance,
        extracted_from=extracted_from,
        confidence=confidence
    )
    # Embed and index
    emb = get_embedding(goal_text)
    if emb is not None:
        memory_manager.save_embedding(
            source_table="goals",
            source_id=goal_id,
            content_text=goal_text,
            embedding=emb
        )
        # Pre-warm cache with the embedding we just computed
        _entity_embedding_cache[("goal", goal_id)] = emb
        
        # Cache entity-to-entity relations
        _cache_top_semantic_links("goals", goal_id, goal_text, top_k=3)
        
    _trigger_graph_export()
    return goal_id


def save_project_semantic(session_id: str, project_name: str, description: str, extracted_from: int = None, confidence: float = 1.0) -> int:
    """
    Calculates importance, saves the project to projects table, and indexes it in vector_memory.
    """
    combined_text = f"Project {project_name}: {description}"
    importance = calculate_importance(combined_text, "")
    proj_id = memory_manager.save_project(
        session_id=session_id,
        project_name=project_name,
        description=description,
        importance_score=importance,
        extracted_from=extracted_from,
        confidence=confidence
    )
    # Embed and index
    emb = get_embedding(combined_text)
    if emb is not None:
        memory_manager.save_embedding(
            source_table="projects",
            source_id=proj_id,
            content_text=combined_text,
            embedding=emb
        )
        # Pre-warm cache with the embedding we just computed
        _entity_embedding_cache[("project", proj_id)] = emb
        
        # Cache entity-to-entity relations
        _cache_top_semantic_links("projects", proj_id, combined_text, top_k=3)
        
    _trigger_graph_export()
    return proj_id


def save_preference_semantic(session_id: str, preference_text: str, extracted_from: int = None, confidence: float = 1.0) -> int:
    """
    Calculates importance, saves the preference to preferences table, and indexes it in vector_memory.
    """
    importance = calculate_importance(preference_text, "")
    pref_id = memory_manager.save_preference(
        session_id=session_id,
        preference_text=preference_text,
        importance_score=importance,
        extracted_from=extracted_from,
        confidence=confidence
    )
    # Embed and index
    emb = get_embedding(preference_text)
    if emb is not None:
        memory_manager.save_embedding(
            source_table="preferences",
            source_id=pref_id,
            content_text=preference_text,
            embedding=emb
        )
        # Pre-warm cache with the embedding we just computed
        _entity_embedding_cache[("preference", pref_id)] = emb
        
        # Cache entity-to-entity relations
        _cache_top_semantic_links("preferences", pref_id, preference_text, top_k=3)
        
    _trigger_graph_export()
    return pref_id


def save_correction_semantic(session_id: str, mistake_context: str, corrected_fact: str, extracted_from: int = None, confidence: float = 1.0) -> int:
    """
    Calculates importance, saves the correction to corrections table, and indexes it in vector_memory.
    """
    combined_text = f"Correction: Previously thought '{mistake_context}', but the truth is '{corrected_fact}'"
    importance = calculate_importance(combined_text, "")
    corr_id = memory_manager.save_correction(
        session_id=session_id,
        mistake_context=mistake_context,
        corrected_fact=corrected_fact,
        importance_score=importance,
        extracted_from=extracted_from,
        confidence=confidence
    )
    # Embed and index
    emb = get_embedding(combined_text)
    if emb is not None:
        memory_manager.save_embedding(
            source_table="corrections",
            source_id=corr_id,
            content_text=combined_text,
            embedding=emb
        )
        # Pre-warm cache with the embedding we just computed
        _entity_embedding_cache[("correction", corr_id)] = emb
        
        # Cache entity-to-entity relations
        _cache_top_semantic_links("corrections", corr_id, combined_text, top_k=3)
        
    _trigger_graph_export()
    return corr_id


def record_retrieved_memories(matches: list):
    """
    Records the IDs of memories retrieved in the last semantic search for RAG.
    This is called when RAG context is injected during chat.
    """
    try:
        from datetime import datetime
        conn = memory_manager._get_connection()
        cursor = conn.cursor()
        
        # Clear previous retrieval
        cursor.execute("DELETE FROM retrieved_memories")
        
        for match in matches:
            cursor.execute("""
                INSERT INTO retrieved_memories (source_table, source_id, timestamp)
                VALUES (?, ?, ?)
            """, (
                match["source_table"],
                match["source_id"],
                datetime.now().isoformat()
            ))
            
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [VectorMemory] Error recording retrieved memories: {e}")


def save_trajectory_semantic(goal: str, steps_json: str, status: str, summary: str = None) -> int:
    """Saves the trajectory to DB and indexes the goal text in vector_memory."""
    traj_id = memory_manager.save_trajectory(goal, steps_json, status, summary)
    emb = get_embedding(goal)
    if emb is not None:
        memory_manager.save_embedding("task_trajectories", traj_id, goal, emb)
    return traj_id


def semantic_search_trajectories(query_text: str, top_k: int = 2) -> list:
    """Searches past task trajectories by goal semantic similarity."""
    query_emb = get_embedding(query_text)
    if query_emb is None:
        return []

    embeddings_list = memory_manager.load_embeddings("task_trajectories")
    if not embeddings_list:
        return []

    scored_trajectories = []
    for item in embeddings_list:
        sim = cosine_similarity(query_emb, item["embedding"])
        if sim < 0.35:
            continue
        
        traj_details = memory_manager.load_trajectory_by_id(item["source_id"])
        if traj_details:
            traj_details["similarity"] = round(sim, 4)
            scored_trajectories.append(traj_details)

    scored_trajectories.sort(key=lambda x: x["similarity"], reverse=True)
    return scored_trajectories[:top_k]


