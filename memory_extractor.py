"""
✨ PANDA — Memory Extraction Layer  (Pre-Sprint 4 Hardening)
=============================================================
The "who decides to save" logic.

Before this module existed, entity tables (goals, projects, preferences,
corrections) were only populated when the user explicitly triggered tool
commands like "add a goal to become CEO".

This module runs in the BACKGROUND after every non-trivial conversation turn
and asks the LLM:

    "Did the user just reveal a goal, project, preference, or correction?"

If yes → check for duplicates → save or increment mention count.

Pipeline:

    User message + Assistant response
              ↓
    extract_memory_entities()       ← LLM prompt, returns structured JSON
              ↓
    process_extracted_entities()    ← dedup + save
              ↓
    save_goal_semantic / save_project_semantic / ...

Architecture:
    vector_memory.save_turn_semantic()  →  memory_extractor.extract_and_save()
    (same background thread — no extra latency for the user)

What you're learning:
    - LLM-as-extractor: using a language model for structured data extraction
    - Background processing: heavy work that doesn't block the user
    - Deduplication: cosine similarity to prevent double entries
    - Graceful degradation: if Ollama is down, extraction silently skips
"""

from __future__ import annotations
import json
import os

# ─── LLM config (same as alya.py) ────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")

# ─── Duplicate detection threshold ───────────────────────────────────────────
# 0.85 is a high bar — "Become CEO" and "Become CTO" are ~0.82 similar,
# so they would correctly be treated as separate entities.
DUPLICATE_THRESHOLD = 0.85


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

EXTRACTION_PROMPT = """You are PANDA's memory extraction engine.
Your ONLY job: Read the conversation turn below and extract any structured entities the user revealed.

Entity types:
1. goals: Concrete user aspirations (e.g., "become a CEO", "learn Japanese").
2. projects: Active projects with name and description (e.g., {"name": "Alya", "description": "Python assistant"}).
3. preferences: Personal preferences/opinions (e.g., "I prefer Python over JavaScript").
4. corrections: Explicit user corrections containing correction language ("actually", "no I meant", "correction").

CRITICAL RULES:
- Be conservative. Only extract with >80% confidence.
- Do NOT extract from questions, hypotheticals, greetings, or meta-conversations.
- Reply with ONLY valid JSON. No markdown or explanations.

OUTPUT FORMAT:
{
  "goals": [],
  "projects": [],
  "preferences": [],
  "corrections": []
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# LLM EXTRACTION CALL
# ═══════════════════════════════════════════════════════════════════════════════

def extract_memory_entities(user_message: str, assistant_response: str) -> dict:
    """
    Sends the conversation turn to the LLM and asks it to extract structured
    entities (goals, projects, preferences, corrections).

    Returns a dict like:
        {"goals": [...], "projects": [...], "preferences": [...], "corrections": [...]}

    Returns empty dict on any failure (LLM down, bad JSON, etc.)
    """
    try:
        import ollama

        client = ollama.Client(
            host=OLLAMA_URL,
            timeout=120.0,
            headers={"ngrok-skip-browser-warning": "true"}
        )

        user_turn = (
            f"USER said: \"{user_message}\"\n"
            f"ASSISTANT replied: \"{assistant_response}\""
        )

        response = client.chat(
            model=MODEL_NAME,
            format='json',
            messages=[
                {'role': 'system', 'content': EXTRACTION_PROMPT},
                {'role': 'user', 'content': user_turn}
            ],
            options={'temperature': 0.1}  # Low temp for consistent extraction
        )

        raw = response['message']['content'].strip()
        data = json.loads(raw)

        # Validate structure — ensure all expected keys exist and are lists
        result = {
            "goals": [],
            "projects": [],
            "preferences": [],
            "corrections": []
        }

        if isinstance(data.get("goals"), list):
            result["goals"] = [g for g in data["goals"] if isinstance(g, str) and g.strip()]

        if isinstance(data.get("projects"), list):
            for p in data["projects"]:
                if isinstance(p, dict) and p.get("name") and p.get("description"):
                    result["projects"].append(p)

        if isinstance(data.get("preferences"), list):
            result["preferences"] = [p for p in data["preferences"] if isinstance(p, str) and p.strip()]

        if isinstance(data.get("corrections"), list):
            for c in data["corrections"]:
                if isinstance(c, dict) and c.get("mistake") and c.get("correction"):
                    result["corrections"].append(c)

        return result

    except ImportError:
        print("  [MemoryExtractor] ollama package not installed -- skipping extraction.")
        return {}
    except Exception as e:
        # Graceful degradation: if Ollama is down, skip silently
        print(f"  [MemoryExtractor] Extraction failed (non-fatal): {e}")
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# DUPLICATE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _is_duplicate_goal(new_text: str, new_emb: list, session_id: str) -> bool:
    """
    Checks if a goal with similar meaning already exists.
    If duplicate found → increments mention count and returns True.
    If no duplicate → returns False (caller should insert new).
    """
    import memory_manager
    from vector_memory import _get_cached_embedding, cosine_similarity, _has_been_mentioned_this_session

    goals = memory_manager.load_goals()
    for goal in goals:
        goal_emb = _get_cached_embedding("goal", goal["id"], goal["goal_text"])
        if goal_emb:
            sim = cosine_similarity(new_emb, goal_emb)
            if sim >= DUPLICATE_THRESHOLD:
                if not _has_been_mentioned_this_session(session_id, "goal", goal["id"]):
                    memory_manager.increment_goal_mention(goal["id"])
                    print(f"  [MemoryExtractor] Duplicate goal detected: '{new_text}' ~= '{goal['goal_text']}' (sim={sim:.2f}) -- incremented mention.")
                else:
                    print(f"  [MemoryExtractor] Duplicate goal '{new_text}' already counted this session -- skipping.")
                return True
    return False


def _is_duplicate_project(new_name: str, new_desc: str, new_emb: list, session_id: str) -> bool:
    """
    Checks if a project with similar meaning already exists.
    """
    import memory_manager
    from vector_memory import _get_cached_embedding, cosine_similarity, _has_been_mentioned_this_session

    projects = memory_manager.load_projects()
    for proj in projects:
        proj_text = f"Project {proj['project_name']}: {proj['description']}"
        proj_emb = _get_cached_embedding("project", proj["id"], proj_text)
        if proj_emb:
            sim = cosine_similarity(new_emb, proj_emb)
            if sim >= DUPLICATE_THRESHOLD:
                if not _has_been_mentioned_this_session(session_id, "project", proj["id"]):
                    memory_manager.increment_project_mention(proj["id"])
                    print(f"  [MemoryExtractor] Duplicate project detected: '{new_name}' ~= '{proj['project_name']}' (sim={sim:.2f}) -- incremented mention.")
                else:
                    print(f"  [MemoryExtractor] Duplicate project '{new_name}' already counted this session -- skipping.")
                return True
    return False


def _is_duplicate_preference(new_text: str, new_emb: list, session_id: str) -> bool:
    """
    Checks if a preference with similar meaning already exists.
    """
    import memory_manager
    from vector_memory import _get_cached_embedding, cosine_similarity, _has_been_mentioned_this_session

    preferences = memory_manager.load_preferences()
    for pref in preferences:
        pref_emb = _get_cached_embedding("preference", pref["id"], pref["preference_text"])
        if pref_emb:
            sim = cosine_similarity(new_emb, pref_emb)
            if sim >= DUPLICATE_THRESHOLD:
                if not _has_been_mentioned_this_session(session_id, "preference", pref["id"]):
                    memory_manager.increment_preference_mention(pref["id"])
                    print(f"  [MemoryExtractor] Duplicate preference detected: '{new_text}' ~= '{pref['preference_text']}' (sim={sim:.2f}) -- incremented mention.")
                else:
                    print(f"  [MemoryExtractor] Duplicate preference '{new_text}' already counted this session -- skipping.")
                return True
    return False


def _is_duplicate_correction(new_mistake: str, new_correction: str, new_emb: list, session_id: str) -> bool:
    """
    Checks if a correction with similar meaning already exists.
    """
    import memory_manager
    from vector_memory import _get_cached_embedding, cosine_similarity, _has_been_mentioned_this_session

    corrections = memory_manager.load_corrections()
    for corr in corrections:
        corr_text = f"Correction: Previously thought '{corr['mistake_context']}', but the truth is '{corr['corrected_fact']}'"
        corr_emb = _get_cached_embedding("correction", corr["id"], corr_text)
        if corr_emb:
            sim = cosine_similarity(new_emb, corr_emb)
            if sim >= DUPLICATE_THRESHOLD:
                if not _has_been_mentioned_this_session(session_id, "correction", corr["id"]):
                    memory_manager.increment_correction_mention(corr["id"])
                    print(f"  [MemoryExtractor] Duplicate correction detected (sim={sim:.2f}) -- incremented mention.")
                else:
                    print(f"  [MemoryExtractor] Duplicate correction already counted this session -- skipping.")
                return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# PROCESS + SAVE — the glue between extraction and storage
# ═══════════════════════════════════════════════════════════════════════════════

def process_extracted_entities(session_id: str, entities: dict, interaction_id: int):
    """
    Takes the structured entities from extract_memory_entities() and:
    1. Checks for duplicates (cosine similarity against existing entities)
    2. If duplicate → increment mention count (respecting session cooldown)
    3. If new → save via vector_memory's save_*_semantic() functions

    Parameters:
        session_id: Current session ID
        entities: Dict from extract_memory_entities()
        interaction_id: The interaction row ID (for extracted_from tracking)
    """
    import vector_memory

    # ── Goals ─────────────────────────────────────────────────────────────────
    for goal_text in entities.get("goals", []):
        try:
            emb = vector_memory.get_embedding(goal_text)
            if emb is None:
                continue
            if not _is_duplicate_goal(goal_text, emb, session_id):
                goal_id = vector_memory.save_goal_semantic(
                    session_id=session_id,
                    goal_text=goal_text,
                    extracted_from=interaction_id,
                    confidence=0.75  # Auto-extracted = lower confidence than explicit
                )
                print(f"  [MemoryExtractor] New goal extracted: '{goal_text}' (id={goal_id})")
        except Exception as e:
            print(f"  [MemoryExtractor] Error saving goal '{goal_text}': {e}")

    # ── Projects ──────────────────────────────────────────────────────────────
    for proj in entities.get("projects", []):
        try:
            proj_name = proj["name"]
            proj_desc = proj["description"]
            combined_text = f"Project {proj_name}: {proj_desc}"
            emb = vector_memory.get_embedding(combined_text)
            if emb is None:
                continue
            if not _is_duplicate_project(proj_name, proj_desc, emb, session_id):
                proj_id = vector_memory.save_project_semantic(
                    session_id=session_id,
                    project_name=proj_name,
                    description=proj_desc,
                    extracted_from=interaction_id,
                    confidence=0.75
                )
                print(f"  [MemoryExtractor] New project extracted: '{proj_name}' (id={proj_id})")
        except Exception as e:
            print(f"  [MemoryExtractor] Error saving project '{proj.get('name', '?')}': {e}")

    # ── Preferences ───────────────────────────────────────────────────────────
    for pref_text in entities.get("preferences", []):
        try:
            emb = vector_memory.get_embedding(pref_text)
            if emb is None:
                continue
            if not _is_duplicate_preference(pref_text, emb, session_id):
                pref_id = vector_memory.save_preference_semantic(
                    session_id=session_id,
                    preference_text=pref_text,
                    extracted_from=interaction_id,
                    confidence=0.75
                )
                print(f"  [MemoryExtractor] New preference extracted: '{pref_text}' (id={pref_id})")
        except Exception as e:
            print(f"  [MemoryExtractor] Error saving preference '{pref_text}': {e}")

    # ── Corrections ───────────────────────────────────────────────────────────
    for corr in entities.get("corrections", []):
        try:
            mistake = corr["mistake"]
            correction = corr["correction"]
            combined_text = f"Correction: Previously thought '{mistake}', but the truth is '{correction}'"
            emb = vector_memory.get_embedding(combined_text)
            if emb is None:
                continue
            if not _is_duplicate_correction(mistake, correction, emb, session_id):
                corr_id = vector_memory.save_correction_semantic(
                    session_id=session_id,
                    mistake_context=mistake,
                    corrected_fact=correction,
                    extracted_from=interaction_id,
                    confidence=0.70  # Corrections are hardest to auto-detect
                )
                print(f"  [MemoryExtractor] New correction extracted: '{mistake}' -> '{correction}' (id={corr_id})")
        except Exception as e:
            print(f"  [MemoryExtractor] Error saving correction: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — called from vector_memory.save_turn_semantic()
# ═══════════════════════════════════════════════════════════════════════════════

def extract_and_save(session_id: str, user_message: str, assistant_response: str, interaction_id: int):
    """
    Full pipeline: Extract → Deduplicate → Save.
    Called from save_turn_semantic() in the same background thread.

    Parameters:
        session_id: Current session ID
        user_message: What the user said
        assistant_response: What PANDA replied
        interaction_id: The interaction row ID for extracted_from tracking
    """
    entities = extract_memory_entities(user_message, assistant_response)

    if not entities:
        return  # LLM down or empty extraction

    # Count how many entities were extracted
    total = (
        len(entities.get("goals", []))
        + len(entities.get("projects", []))
        + len(entities.get("preferences", []))
        + len(entities.get("corrections", []))
    )

    if total == 0:
        return  # Nothing to extract from this turn

    print(f"  [MemoryExtractor] Extracted {total} entities from turn -- processing...")
    process_extracted_entities(session_id, entities, interaction_id)
