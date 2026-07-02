"""
✨ PANDA — Memory Manager (SQLite)
====================================
The low-level persistence layer — talks directly to SQLite.

Database: memory/panda_memory.db

Table: conversations
    ┌────────────┬──────────────────────────────────────────────┐
    │ Field      │ Purpose                                      │
    ├────────────┼──────────────────────────────────────────────┤
    │ id         │ Unique message ID (auto-increment)           │
    │ session_id │ Identifies one chat session (e.g. session_92)│
    │ role       │ 'user' or 'assistant'                        │
    │ content    │ The actual message text                      │
    │ timestamp  │ When the message was recorded (ISO 8601)     │
    └────────────┴──────────────────────────────────────────────┘

Architecture rule:
    memory_manager.py  →  raw SQLite operations (INSERT, SELECT)
    conversation_manager.py  →  brain state logic (trimming, context, restoration)

What you're learning here:
- SQLite — a serverless, file-based relational database
- SQL DDL — CREATE TABLE, data types, constraints
- SQL DML — INSERT, SELECT with ORDER BY and LIMIT
- Python's built-in `sqlite3` module — no pip install needed
- Sequential ID generation from database queries
"""

import sqlite3
import os
from datetime import datetime, timedelta

# ─── DATABASE PATH ────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DIR = os.path.join(_HERE, "memory")
DB_PATH = os.path.join(MEMORY_DIR, "panda_memory.db")


def _ensure_memory_dir():
    """Creates the memory/ directory if it doesn't exist yet."""
    os.makedirs(MEMORY_DIR, exist_ok=True)


def _get_connection() -> sqlite3.Connection:
    """
    Returns a connection to the SQLite database.
    Creates the memory/ directory and the .db file if they don't exist.
    """
    _ensure_memory_dir()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL mode allows concurrent reads while writing — crucial for background threads
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_db_stats() -> dict:
    """
    Returns diagnostic statistics about the database.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM interactions")
        cnt_int = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM vector_memory")
        cnt_vec = cursor.fetchone()[0]
        return {
            "interactions_count": cnt_int,
            "vector_memory_count": cnt_vec
        }
    except Exception:
        return {
            "interactions_count": 0,
            "vector_memory_count": 0
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def initialize_memory():
    """
    Creates the memory/ folder, the database file, and the conversations table.
    Idempotent — safe to call every time PANDA starts.
    """
    conn = _get_connection()
    try:
        _initialize_memory_tables(conn)
    finally:
        conn.close()

def _initialize_memory_tables(conn):
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL,
            role        TEXT    NOT NULL CHECK(role IN ('user', 'assistant')),
            content     TEXT    NOT NULL,
            timestamp   TEXT    NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversations_session
        ON conversations (session_id)
    """)

    # New structured interactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          TEXT    NOT NULL,
            user_message        TEXT    NOT NULL,
            assistant_response  TEXT    NOT NULL,
            importance_score    REAL    NOT NULL DEFAULT 0.1,
            timestamp           TEXT    NOT NULL
        )
    """)

    # New vector memory table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vector_memory (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            source_table  TEXT    NOT NULL,
            source_id     INTEGER NOT NULL,
            content_text  TEXT    NOT NULL,
            embedding     BLOB    NOT NULL
        )
    """)

    # New structured goals table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id                            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id                    TEXT    NOT NULL,
            goal_text                     TEXT    NOT NULL,
            status                        TEXT    NOT NULL DEFAULT 'active',
            importance_score              REAL    NOT NULL DEFAULT 0.5,
            extracted_from_interaction_id INTEGER REFERENCES interactions(id),
            confidence                    REAL    NOT NULL DEFAULT 1.0,
            mention_count                 INTEGER DEFAULT 1,
            created_at                    TEXT    NOT NULL,
            updated_at                    TEXT    NOT NULL
        )
    """)

    # New structured projects table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id                            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id                    TEXT    NOT NULL,
            project_name                  TEXT    NOT NULL,
            description                   TEXT    NOT NULL,
            importance_score              REAL    NOT NULL DEFAULT 0.5,
            extracted_from_interaction_id INTEGER REFERENCES interactions(id),
            confidence                    REAL    NOT NULL DEFAULT 1.0,
            mention_count                 INTEGER DEFAULT 1,
            created_at                    TEXT    NOT NULL,
            updated_at                    TEXT    NOT NULL
        )
    """)

    # New structured preferences table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            id                            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id                    TEXT    NOT NULL,
            preference_text               TEXT    NOT NULL,
            importance_score              REAL    NOT NULL DEFAULT 0.5,
            extracted_from_interaction_id INTEGER REFERENCES interactions(id),
            confidence                    REAL    NOT NULL DEFAULT 1.0,
            mention_count                 INTEGER DEFAULT 1,
            created_at                    TEXT    NOT NULL,
            updated_at                    TEXT    NOT NULL
        )
    """)

    # New structured corrections table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS corrections (
            id                            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id                    TEXT    NOT NULL,
            mistake_context               TEXT    NOT NULL,
            corrected_fact                TEXT    NOT NULL,
            importance_score              REAL    NOT NULL DEFAULT 0.5,
            extracted_from_interaction_id INTEGER REFERENCES interactions(id),
            confidence                    REAL    NOT NULL DEFAULT 1.0,
            mention_count                 INTEGER DEFAULT 1,
            created_at                    TEXT    NOT NULL,
            updated_at                    TEXT    NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_interactions_session
        ON interactions (session_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_vector_memory_source
        ON vector_memory (source_table, source_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_goals_session
        ON goals (session_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_projects_session
        ON projects (session_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_preferences_session
        ON preferences (session_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_corrections_session
        ON corrections (session_id)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_links (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            source_table        TEXT    NOT NULL,
            source_id           INTEGER NOT NULL,
            target_table        TEXT    NOT NULL,
            target_id           INTEGER NOT NULL,
            similarity_score    REAL    NOT NULL,
            link_type           TEXT    NOT NULL,
            created_at          TEXT    NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_entity_links_source
        ON entity_links (source_table, source_id)
    """)

    # Active retrieval tracking table for visualization
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS retrieved_memories (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            source_table  TEXT    NOT NULL,
            source_id     INTEGER NOT NULL,
            timestamp     TEXT    NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_retrieved_memories_source
        ON retrieved_memories (source_table, source_id)
    """)

    # --- Sprint 5 Schemas ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_summaries (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT UNIQUE,
            summary_text  TEXT NOT NULL,
            key_takeaways TEXT NOT NULL,
            created_at    TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reflections (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            reflection_type   TEXT NOT NULL,
            insight_text      TEXT NOT NULL,
            category          TEXT NOT NULL,
            importance_score  REAL NOT NULL DEFAULT 0.5,
            created_at        TEXT NOT NULL
        )
    """)

    # --- Sprint 6 Schemas ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goal_steps (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id         INTEGER NOT NULL REFERENCES goals(id),
            plan_version    INTEGER NOT NULL DEFAULT 1,
            step_number     INTEGER NOT NULL,
            step_text       TEXT    NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'pending',
            depends_on      INTEGER REFERENCES goal_steps(id),
            notes           TEXT    DEFAULT '',
            created_at      TEXT    NOT NULL,
            updated_at      TEXT    NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_goal_steps_goal_version
        ON goal_steps (goal_id, plan_version)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goal_plans (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id         INTEGER NOT NULL REFERENCES goals(id),
            plan_version    INTEGER NOT NULL DEFAULT 1,
            generated_by    TEXT    NOT NULL DEFAULT 'ollama',
            generated_at    TEXT    NOT NULL,
            model_used      TEXT    NOT NULL,
            raw_plan_json   TEXT    NOT NULL,
            UNIQUE(goal_id, plan_version)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_goal_plans_goal_version
        ON goal_plans (goal_id, plan_version)
    """)

    # --- Sprint 7 Schemas ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS screen_observations (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id            TEXT NOT NULL,
            observation_text      TEXT NOT NULL,
            raw_ocr_text          TEXT,
            active_window         TEXT,
            parent_observation_id INTEGER REFERENCES screen_observations(id),
            importance_score      REAL DEFAULT 0.5,
            created_at            TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_screen_observations_session
        ON screen_observations (session_id)
    """)

    # --- Sprint 8 Schemas ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL,
            action_type TEXT    NOT NULL,
            target      TEXT,
            coords_x    INTEGER,
            coords_y    INTEGER,
            success     INTEGER NOT NULL DEFAULT 0,
            verified    INTEGER NOT NULL DEFAULT 0,
            error_msg   TEXT,
            created_at  TEXT    NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_log_session
        ON action_log (session_id)
    """)

    # Idempotent migration for consolidated_to column in entity tables
    for table in ['goals', 'projects', 'preferences']:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = {row["name"] for row in cursor.fetchall()}
        if "consolidated_to" not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN consolidated_to INTEGER REFERENCES {table}(id)")
            print(f"  [MemoryManager] Migrated {table} table: added consolidated_to column.")

    # Idempotent migration for goals table new columns
    cursor.execute("PRAGMA table_info(goals)")
    goals_cols = {row["name"] for row in cursor.fetchall()}
    new_goals_cols = {
        "priority": "INTEGER DEFAULT 5",
        "manual_priority_weight": "REAL DEFAULT 0.0",
        "completion_velocity": "REAL DEFAULT 0.0",
        "target_date": "TEXT DEFAULT NULL",
        "parent_goal_id": "INTEGER REFERENCES goals(id) DEFAULT NULL",
        "progress_pct": "REAL DEFAULT 0.0",
        "current_plan_version": "INTEGER DEFAULT 0"
    }
    for col_name, col_def in new_goals_cols.items():
        if col_name not in goals_cols:
            cursor.execute(f"ALTER TABLE goals ADD COLUMN {col_name} {col_def}")
            print(f"  [MemoryManager] Migrated goals table: added {col_name} column.")

    # --- Sprint 9 Schemas ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_trajectories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            goal        TEXT    NOT NULL,
            steps_json  TEXT    NOT NULL,
            status      TEXT    NOT NULL,
            summary     TEXT,
            created_at  TEXT    NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_trajectories_status
        ON task_trajectories (status)
    """)

    # --- Lessons Learned (Plan 2) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id       TEXT    NOT NULL,
            lesson_text      TEXT    NOT NULL,
            importance_score REAL    NOT NULL DEFAULT 0.5,
            created_at       TEXT    NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lessons_session
        ON lessons (session_id)
    """)

    # --- Todos Schema ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            task                    TEXT    NOT NULL,
            done                    INTEGER NOT NULL DEFAULT 0,
            created_at              TEXT    NOT NULL,
            deadline                TEXT    DEFAULT NULL,
            reminder_minutes_before INTEGER NOT NULL DEFAULT 15,
            reminded                INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 9 — SESSION ID GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_session_id() -> str:
    """
    Creates a timestamp-based session ID like: session_20260601_121522

    Why timestamp instead of sequential?
      - No DB scan needed — O(1) instead of O(N)
      - No race conditions — two threads can't generate the same timestamp
        (microsecond suffix added as tiebreaker if needed)
      - Deletion-safe — deleting session_999 doesn't break the next ID
      - Human-readable — you can see exactly when PANDA was used
      - Sortable — sessions are naturally ordered by creation time
      - Analyzable — usage patterns are visible from the ID itself

    Format: session_YYYYMMDD_HHMMSS_ffffff
      The microsecond suffix (_ffffff) is always included to guarantee
      uniqueness even if two sessions start in the same second.
    """
    now = datetime.now()
    return f"session_{now.strftime('%Y%m%d_%H%M%S')}_{now.strftime('%f')}"


# ═══════════════════════════════════════════════════════════════════════════════
# SAVE MESSAGE
# ═══════════════════════════════════════════════════════════════════════════════

def save_message(session_id: str, role: str, content: str):
    """
    Inserts one message into the conversations table.
    Timestamp is auto-added. Uses parameterized queries (?) for SQL safety.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
        """, (
            session_id,
            role,
            content,
            datetime.now().isoformat()
        ))
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD MESSAGES
# ═══════════════════════════════════════════════════════════════════════════════

def load_session_messages(session_id: str, limit: int = 20) -> list:
    """
    Retrieves the most recent messages from a specific session.

    Returns Ollama-ready format:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    Args:
        session_id — which session to load from
        limit      — max messages to return (default 20 = 10 turns)
    """
    conn = _get_connection()
    rows = []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content FROM (
                SELECT role, content, id
                FROM conversations
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) sub
            ORDER BY id ASC
        """, (session_id, limit))
        rows = cursor.fetchall()
    finally:
        conn.close()

    return [{"role": row["role"], "content": row["content"]} for row in rows]


def get_last_session_id() -> str | None:
    """
    Returns the session_id of the most recent conversation.
    Returns None if the database is empty (first run).

    Used by conversation_manager.py for startup restoration (Step 13).
    """
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT session_id FROM conversations
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()

    return row["session_id"] if row else None


def get_session_summary(session_id: str, limit: int = 6) -> list:
    """
    Loads the first few messages from a session — used to generate
    a 'last time we discussed...' summary at startup.

    Returns the first `limit` messages (3 full turns) from the session.
    """
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT role, content FROM conversations
        WHERE session_id = ?
        ORDER BY id ASC
        LIMIT ?
    """, (session_id, limit))

    rows = cursor.fetchall()
    conn.close()

    return [{"role": row["role"], "content": row["content"]} for row in rows]


def save_interaction(session_id: str, user_message: str, assistant_response: str, importance_score: float) -> int:
    """
    Saves a full conversation turn to the interactions table.
    Returns the ID of the newly inserted row.
    """
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO interactions (session_id, user_message, assistant_response, importance_score, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (
        session_id,
        user_message,
        assistant_response,
        importance_score,
        datetime.now().isoformat()
    ))

    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def save_embedding(source_table: str, source_id: int, content_text: str, embedding: list):
    """
    Saves an embedding array (list of float) into the vector_memory table.
    Unpacking and packing is done via python's struct module.
    """
    import struct
    embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)

    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO vector_memory (source_table, source_id, content_text, embedding)
        VALUES (?, ?, ?, ?)
    """, (
        source_table,
        source_id,
        content_text,
        embedding_bytes
    ))

    conn.commit()
    conn.close()


def load_embeddings(source_table: str = None) -> list:
    """
    Loads all embeddings from the database. Optionally filtered by source_table.
    Unpacks binary BLOBs back into float list.
    """
    import struct

    conn = _get_connection()
    cursor = conn.cursor()

    if source_table:
        cursor.execute("""
            SELECT id, source_table, source_id, content_text, embedding
            FROM vector_memory
            WHERE source_table = ?
        """, (source_table,))
    else:
        cursor.execute("""
            SELECT id, source_table, source_id, content_text, embedding
            FROM vector_memory
        """)

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        emb_blob = row["embedding"]
        num_floats = len(emb_blob) // 4
        if num_floats > 0:
            emb_list = list(struct.unpack(f"{num_floats}f", emb_blob))
        else:
            emb_list = []
        results.append({
            "id": row["id"],
            "source_table": row["source_table"],
            "source_id": row["source_id"],
            "content_text": row["content_text"],
            "embedding": emb_list
        })
    return results


def load_interactions_with_embeddings() -> list:
    """
    Loads interactions joined with their vector embeddings from the database.
    """
    import struct
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.id, i.session_id, i.user_message, i.assistant_response, 
               i.importance_score, i.timestamp, v.embedding
        FROM interactions i
        JOIN vector_memory v ON v.source_table = 'interactions' AND v.source_id = i.id
    """)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        emb_blob = row["embedding"]
        num_floats = len(emb_blob) // 4
        if num_floats > 0:
            emb_list = list(struct.unpack(f"{num_floats}f", emb_blob))
        else:
            emb_list = []
        results.append({
            "id": row["id"],
            "session_id": row["session_id"],
            "user_message": row["user_message"],
            "assistant_response": row["assistant_response"],
            "importance_score": row["importance_score"],
            "timestamp": row["timestamp"],
            "embedding": emb_list
        })
    return results


def save_goal(session_id: str, goal_text: str, status: str = 'active', importance_score: float = 0.95, extracted_from: int = None, confidence: float = 1.0) -> int:
    """Saves a goal to the goals table. Returns the new goal's ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO goals (session_id, goal_text, status, importance_score, extracted_from_interaction_id, confidence, mention_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
    """, (session_id, goal_text, status, importance_score, extracted_from, confidence, now_iso, now_iso))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def save_project(session_id: str, project_name: str, description: str, importance_score: float = 0.75, extracted_from: int = None, confidence: float = 1.0) -> int:
    """Saves a project to the projects table. Returns the new project's ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO projects (session_id, project_name, description, importance_score, extracted_from_interaction_id, confidence, mention_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
    """, (session_id, project_name, description, importance_score, extracted_from, confidence, now_iso, now_iso))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def increment_goal_mention(goal_id: int):
    """Increments mention_count for a goal, boosts importance_score by 0.10 (max 1.0), and updates updated_at."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        UPDATE goals 
        SET mention_count = mention_count + 1, 
            importance_score = MIN(1.0, importance_score + 0.10),
            updated_at = ?
        WHERE id = ?
    """, (now_iso, goal_id))
    conn.commit()
    conn.close()


def increment_project_mention(project_id: int):
    """Increments mention_count for a project, boosts importance_score by 0.10 (max 1.0), and updates updated_at."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        UPDATE projects 
        SET mention_count = mention_count + 1, 
            importance_score = MIN(1.0, importance_score + 0.10),
            updated_at = ?
        WHERE id = ?
    """, (now_iso, project_id))
    conn.commit()
    conn.close()


def update_goal_status(goal_id: int, status: str):
    """Updates the status of a goal (e.g. 'active' → 'completed') and refreshes updated_at."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        UPDATE goals
        SET status = ?, updated_at = ?
        WHERE id = ?
    """, (status, now_iso, goal_id))
    conn.commit()
    conn.close()


def load_goals(status: str = None) -> list:
    """Loads all goals, optionally filtered by status, excluding consolidated ones."""
    conn = _get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM goals WHERE status = ? AND consolidated_to IS NULL ORDER BY id DESC", (status,))
    else:
        cursor.execute("SELECT * FROM goals WHERE consolidated_to IS NULL ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_goal_step(goal_id: int, plan_version: int, step_number: int, step_text: str, depends_on: int = None) -> int:
    """Saves a step for a specific goal and plan version."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO goal_steps (goal_id, plan_version, step_number, step_text, status, depends_on, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
    """, (goal_id, plan_version, step_number, step_text, depends_on, now_iso, now_iso))
    step_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return step_id


def load_goal_steps(goal_id: int, plan_version: int = None) -> list:
    """Loads steps for a goal. If plan_version is None, loads the latest version's steps."""
    conn = _get_connection()
    cursor = conn.cursor()
    if plan_version is None:
        cursor.execute("SELECT MAX(plan_version) FROM goal_steps WHERE goal_id = ?", (goal_id,))
        row = cursor.fetchone()
        plan_version = row[0] if row and row[0] is not None else 1
    
    cursor.execute("""
        SELECT * FROM goal_steps 
        WHERE goal_id = ? AND plan_version = ?
        ORDER BY step_number ASC
    """, (goal_id, plan_version))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def load_goal_plan_history(goal_id: int) -> list:
    """Loads the plan version metadata history for a goal."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM goal_plans 
        WHERE goal_id = ? 
        ORDER BY plan_version DESC
    """, (goal_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_step_status(step_id: int, status: str):
    """Updates the status of a step (pending | in_progress | done | blocked)."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        UPDATE goal_steps 
        SET status = ?, updated_at = ?
        WHERE id = ?
    """, (status, now_iso, step_id))
    conn.commit()
    conn.close()


def save_goal_plan_meta(goal_id: int, version: int, model: str, raw_json: str):
    """Saves metadata for a generated goal plan version."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT OR REPLACE INTO goal_plans (goal_id, plan_version, generated_by, generated_at, model_used, raw_plan_json)
        VALUES (?, ?, 'ollama', ?, ?, ?)
    """, (goal_id, version, now_iso, model, raw_json))
    conn.commit()
    conn.close()


def load_goal_plan_meta(goal_id: int, version: int = None) -> dict | None:
    """Loads plan version metadata. If version is None, loads the latest version."""
    conn = _get_connection()
    cursor = conn.cursor()
    if version is None:
        cursor.execute("SELECT MAX(plan_version) FROM goal_plans WHERE goal_id = ?", (goal_id,))
        row = cursor.fetchone()
        version = row[0] if row and row[0] is not None else 1
        
    cursor.execute("""
        SELECT * FROM goal_plans 
        WHERE goal_id = ? AND plan_version = ?
    """, (goal_id, version))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_goal_priority(goal_id: int, priority: int, manual_weight: float = None):
    """Updates the priority and optional manual priority weight for a goal."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    if manual_weight is not None:
        cursor.execute("""
            UPDATE goals 
            SET priority = ?, manual_priority_weight = ?, updated_at = ?
            WHERE id = ?
        """, (priority, manual_weight, now_iso, goal_id))
    else:
        cursor.execute("""
            UPDATE goals 
            SET priority = ?, updated_at = ?
            WHERE id = ?
        """, (priority, now_iso, goal_id))
    conn.commit()
    conn.close()


def update_goal_progress(goal_id: int):
    """Recomputes and caches progress_pct for a goal based on its active plan steps."""
    conn = _get_connection()
    cursor = conn.cursor()
    
    # Get current active plan version
    cursor.execute("SELECT current_plan_version FROM goals WHERE id = ?", (goal_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    
    current_ver = row["current_plan_version"]
    if not current_ver or current_ver == 0:
        # Check steps anyway, just in case
        cursor.execute("SELECT MAX(plan_version) FROM goal_steps WHERE goal_id = ?", (goal_id,))
        max_row = cursor.fetchone()
        current_ver = max_row[0] if max_row and max_row[0] is not None else 0
        
    if current_ver == 0:
        conn.close()
        return
        
    cursor.execute("""
        SELECT COUNT(*), SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) 
        FROM goal_steps 
        WHERE goal_id = ? AND plan_version = ?
    """, (goal_id, current_ver))
    res = cursor.fetchone()
    total = res[0]
    done = res[1] if res[1] is not None else 0
    
    progress = 0.0
    if total > 0:
        progress = float(done) / float(total)
        
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        UPDATE goals 
        SET progress_pct = ?, current_plan_version = ?, updated_at = ?
        WHERE id = ?
    """, (progress, current_ver, now_iso, goal_id))
    conn.commit()
    conn.close()


def load_goals_with_steps(status: str = None) -> list:
    """Loads all goals (optionally filtered by status) with their current-version steps joined."""
    conn = _get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM goals WHERE consolidated_to IS NULL"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY id DESC"
    
    cursor.execute(query, params)
    goals = [dict(row) for row in cursor.fetchall()]
    
    for goal in goals:
        goal_id = goal["id"]
        ver = goal["current_plan_version"]
        goal["steps"] = load_goal_steps(goal_id, ver)
    
    conn.close()
    return goals


def get_next_action(goal_id: int) -> dict | None:
    """Returns the first pending step with no unfinished dependencies."""
    steps = load_goal_steps(goal_id)
    if not steps:
        return None
        
    for step in steps:
        if step["status"] in ('pending', 'in_progress'):
            dep = step["depends_on"]
            # If there's a dependency, verify if that dependent step is done
            if dep is not None:
                dep_step = next((s for s in steps if s["id"] == dep), None)
                if dep_step and dep_step["status"] != 'done':
                    # Blocked by dependent step
                    continue
            return step
            
    return None


def get_active_plan_version(goal_id: int) -> int:
    """Returns current_plan_version for a goal."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT current_plan_version FROM goals WHERE id = ?", (goal_id,))
    row = cursor.fetchone()
    conn.close()
    return row["current_plan_version"] if row and row["current_plan_version"] is not None else 0


def load_projects() -> list:
    """Loads all projects."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_preference(session_id: str, preference_text: str, importance_score: float = 0.5, extracted_from: int = None, confidence: float = 1.0) -> int:
    """Saves a preference to the preferences table. Returns the new preference's ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO preferences (session_id, preference_text, importance_score, extracted_from_interaction_id, confidence, mention_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
    """, (session_id, preference_text, importance_score, extracted_from, confidence, now_iso, now_iso))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def save_correction(session_id: str, mistake_context: str, corrected_fact: str, importance_score: float = 0.5, extracted_from: int = None, confidence: float = 1.0) -> int:
    """Saves a correction to the corrections table. Returns the new correction's ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO corrections (session_id, mistake_context, corrected_fact, importance_score, extracted_from_interaction_id, confidence, mention_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
    """, (session_id, mistake_context, corrected_fact, importance_score, extracted_from, confidence, now_iso, now_iso))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def increment_preference_mention(pref_id: int):
    """Increments mention_count for a preference, boosts importance_score by 0.10 (max 1.0), and updates updated_at."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        UPDATE preferences 
        SET mention_count = mention_count + 1, 
            importance_score = MIN(1.0, importance_score + 0.10),
            updated_at = ?
        WHERE id = ?
    """, (now_iso, pref_id))
    conn.commit()
    conn.close()


def increment_correction_mention(corr_id: int):
    """Increments mention_count for a correction, boosts importance_score by 0.10 (max 1.0), and updates updated_at."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        UPDATE corrections 
        SET mention_count = mention_count + 1, 
            importance_score = MIN(1.0, importance_score + 0.10),
            updated_at = ?
        WHERE id = ?
    """, (now_iso, corr_id))
    conn.commit()
    conn.close()


def load_preferences() -> list:
    """Loads all preferences."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM preferences ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def load_corrections() -> list:
    """Loads all corrections."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM corrections ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_lesson(session_id: str, lesson_text: str, importance_score: float = 0.5) -> int:
    """Saves a distilled lesson to the lessons table. Returns the new lesson's ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO lessons (session_id, lesson_text, importance_score, created_at)
        VALUES (?, ?, ?, ?)
    """, (session_id, lesson_text, importance_score, now_iso))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def load_lessons(limit: int = 5) -> list[dict]:
    """Loads most recent lessons up to the limit."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lessons ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def load_all_memories_with_embeddings() -> list:
    """
    Loads all vector memory embeddings enriched with metadata from their respective tables.
    COALESCE is used to merge common fields like session_id, importance_score, and timestamp.
    Excludes entities that have been consolidated (cautious soft-archiving).
    """
    import struct
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.id, v.source_table, v.source_id, v.content_text, v.embedding,
               i.assistant_response as assistant_response,
               COALESCE(i.session_id, g.session_id, p.session_id, pr.session_id, c.session_id, s.session_id) as session_id,
               COALESCE(i.importance_score, g.importance_score, p.importance_score, pr.importance_score, c.importance_score, r.importance_score, 0.3) as importance_score,
               COALESCE(i.timestamp, g.created_at, p.created_at, pr.created_at, c.created_at, r.created_at, s.created_at) as timestamp,
               g.status as goal_status
        FROM vector_memory v
        LEFT JOIN interactions i ON v.source_table = 'interactions' AND v.source_id = i.id
        LEFT JOIN goals g ON v.source_table = 'goals' AND v.source_id = g.id
        LEFT JOIN projects p ON v.source_table = 'projects' AND v.source_id = p.id
        LEFT JOIN preferences pr ON v.source_table = 'preferences' AND v.source_id = pr.id
        LEFT JOIN corrections c ON v.source_table = 'corrections' AND v.source_id = c.id
        LEFT JOIN reflections r ON v.source_table = 'reflections' AND v.source_id = r.id
        LEFT JOIN session_summaries s ON v.source_table = 'session_summaries' AND v.source_id = s.id
        WHERE (g.consolidated_to IS NULL OR v.source_table != 'goals')
          AND (g.status != 'abandoned' OR v.source_table != 'goals')
          AND (p.consolidated_to IS NULL OR v.source_table != 'projects')
          AND (pr.consolidated_to IS NULL OR v.source_table != 'preferences')
        ORDER BY importance_score DESC, timestamp DESC
        LIMIT 2000
    """)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        # Pre-filter by importance score to avoid struct.unpack overhead for garbage
        if row["importance_score"] < 0.10:
            continue
            
        emb_blob = row["embedding"]
        num_floats = len(emb_blob) // 4
        if num_floats > 0:
            emb_list = list(struct.unpack(f"{num_floats}f", emb_blob))
        else:
            emb_list = []
        results.append({
            "id": row["id"],
            "source_table": row["source_table"],
            "source_id": row["source_id"],
            "content_text": row["content_text"],
            "embedding": emb_list,
            "assistant_response": row["assistant_response"],
            "session_id": row["session_id"],
            "importance_score": row["importance_score"],
            "timestamp": row["timestamp"],
            "goal_status": row["goal_status"]
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH EDGES (ENTITY LINKS)
# ═══════════════════════════════════════════════════════════════════════════════

def save_entity_link(source_table: str, source_id: int, target_table: str, target_id: int, similarity_score: float, link_type: str = 'semantic_similarity') -> int:
    """
    Saves a directed edge connecting two memories/entities.
    Returns the new link's ID.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    
    # Avoid duplicate links
    cursor.execute("""
        SELECT id FROM entity_links 
        WHERE source_table = ? AND source_id = ? AND target_table = ? AND target_id = ? AND link_type = ?
    """, (source_table, source_id, target_table, target_id, link_type))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing["id"]

    cursor.execute("""
        INSERT INTO entity_links (source_table, source_id, target_table, target_id, similarity_score, link_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (source_table, source_id, target_table, target_id, similarity_score, link_type, now_iso))
    
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_links_for_entity(entity_table: str, entity_id: int) -> list:
    """
    Gets all links where the given entity is either the source or the target.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM entity_links 
        WHERE (source_table = ? AND source_id = ?) 
           OR (target_table = ? AND target_id = ?)
        ORDER BY similarity_score DESC
    """, (entity_table, entity_id, entity_table, entity_id))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_links() -> list:
    """
    Loads all entity links for graph visualization.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entity_links")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


import json

def save_session_summary(session_id: str, summary_text: str, key_takeaways: list) -> int:
    """Saves a session summary and key takeaways to the database. Returns the summary's ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    created_at = datetime.now().isoformat()
    takeaways_json = json.dumps(key_takeaways)
    
    try:
        cursor.execute("""
            INSERT INTO session_summaries (session_id, summary_text, key_takeaways, created_at)
            VALUES (?, ?, ?, ?)
        """, (session_id, summary_text, takeaways_json, created_at))
        summary_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        cursor.execute("""
            UPDATE session_summaries
            SET summary_text = ?, key_takeaways = ?
            WHERE session_id = ?
        """, (summary_text, takeaways_json, session_id))
        cursor.execute("SELECT id FROM session_summaries WHERE session_id = ?", (session_id,))
        summary_id = cursor.fetchone()[0]
        
    conn.commit()
    conn.close()
    return summary_id


def load_session_summary(session_id: str) -> dict | None:
    """Loads a session summary from the database."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM session_summaries WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        res = dict(row)
        try:
            res["key_takeaways"] = json.loads(res["key_takeaways"])
        except Exception:
            res["key_takeaways"] = []
        return res
    return None


def save_reflection(reflection_type: str, insight_text: str, category: str, importance_score: float = 0.5) -> int:
    """Saves a reflection to the database. Returns the new reflection ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    created_at = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO reflections (reflection_type, insight_text, category, importance_score, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (reflection_type, insight_text, category, importance_score, created_at))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def load_reflections(reflection_type: str = None) -> list:
    """Loads reflections from the database, optionally filtered by type."""
    conn = _get_connection()
    cursor = conn.cursor()
    if reflection_type:
        cursor.execute("SELECT * FROM reflections WHERE reflection_type = ? ORDER BY id DESC", (reflection_type,))
    else:
        cursor.execute("SELECT * FROM reflections ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_memory_importance(table_name: str, row_id: int, new_score: float):
    """Updates the importance score for a specific memory row in any table."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    
    # Safe validation of table name to prevent SQL injection
    allowed_tables = {'interactions', 'goals', 'projects', 'preferences', 'corrections', 'reflections'}
    if table_name not in allowed_tables:
        conn.close()
        raise ValueError(f"Invalid table name for importance update: {table_name}")
        
    if table_name == 'interactions':
        cursor.execute("""
            UPDATE interactions 
            SET importance_score = ?
            WHERE id = ?
        """, (new_score, row_id))
    elif table_name == 'reflections':
        cursor.execute("""
            UPDATE reflections 
            SET importance_score = ?
            WHERE id = ?
        """, (new_score, row_id))
    else:
        cursor.execute(f"""
            UPDATE {table_name} 
            SET importance_score = ?, updated_at = ?
            WHERE id = ?
        """, (new_score, now_iso, row_id))
        
    conn.commit()
    conn.close()


def boost_memory_importance(table_name: str, row_id: int, boost_amount: float = 0.1):
    """Increments the importance score for a specific memory row in any table, updating its timestamp."""
    conn = _get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    
    allowed_tables = {'interactions', 'goals', 'projects', 'preferences', 'corrections', 'reflections'}
    if table_name not in allowed_tables:
        conn.close()
        raise ValueError(f"Invalid table name for importance boost: {table_name}")
        
    if table_name == 'interactions':
        cursor.execute("""
            UPDATE interactions 
            SET importance_score = MIN(1.0, importance_score + ?), timestamp = ?
            WHERE id = ?
        """, (boost_amount, now_iso, row_id))
    elif table_name == 'reflections':
        cursor.execute("""
            UPDATE reflections 
            SET importance_score = MIN(1.0, importance_score + ?)
            WHERE id = ?
        """, (boost_amount, row_id))
    else:
        cursor.execute(f"""
            UPDATE {table_name} 
            SET importance_score = MIN(1.0, importance_score + ?), updated_at = ?
            WHERE id = ?
        """, (boost_amount, now_iso, row_id))
        
    conn.commit()
    conn.close()


def redact_pii_and_credentials(text: str) -> str:
    """Scrub Credit Cards, SSN, standard API keys, and password masks/secrets from text."""
    if not text:
        return text
    import re
    # 1. Credit Cards
    text = re.sub(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b', '[REDACTED_CREDENTIAL]', text)
    # 2. SSN
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_CREDENTIAL]', text)
    # 3. Common API Keys
    text = re.sub(r'\b(sk-[a-zA-Z0-9]{20,}|sk-ant-[a-zA-Z0-9-]{20,}|ghp_[a-zA-Z0-9]{20,})\b', '[REDACTED_CREDENTIAL]', text)
    # 4. Password Mask indicators (length >= 4)
    text = re.sub(r'[•●\*]{4,}', '[REDACTED_CREDENTIAL]', text)
    return text

def add_screen_observation(session_id: str, observation_text: str, raw_ocr_text: str, active_window: str, parent_observation_id: int = None) -> int:
    """Saves a new screen observation to the database. Returns the new observation ID."""
    observation_text = redact_pii_and_credentials(observation_text)
    raw_ocr_text = redact_pii_and_credentials(raw_ocr_text)
    
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        created_at = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO screen_observations (session_id, observation_text, raw_ocr_text, active_window, parent_observation_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, observation_text, raw_ocr_text, active_window, parent_observation_id, created_at))
        row_id = cursor.lastrowid
        conn.commit()
        
        # Auto-prune observations to prevent DB bloat (keep last 500)
        try:
            cursor.execute("""
                DELETE FROM screen_observations
                WHERE id NOT IN (
                    SELECT id FROM screen_observations
                    ORDER BY id DESC
                    LIMIT 500
                )
            """)
            conn.commit()
        except Exception as prune_err:
            print(f"⚠️ [Prune] Failed to prune screen observations: {prune_err}")
            
        return row_id
    finally:
        conn.close()


def get_recent_observations(session_id: str, limit: int = 3) -> list[dict]:
    """Loads the most recent screen observations for a session, ordered by ID descending."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM screen_observations
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (session_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_observation_chain(observation_id: int) -> list[dict]:
    """Follows the parent_observation_id chain backwards from observation_id and returns the list of observations in chronological order (oldest to newest)."""
    conn = _get_connection()
    chain = []
    current_id = observation_id
    visited = set()
    while current_id is not None and current_id not in visited:
        visited.add(current_id)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM screen_observations WHERE id = ?", (current_id,))
        row = cursor.fetchone()
        if not row:
            break
        obs = dict(row)
        chain.append(obs)
        current_id = obs["parent_observation_id"]
    conn.close()
    chain.reverse()
    return chain



# ═══════════════════════════════════════════════════════════════════════════════
# RUN DIRECTLY TO TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n  PANDA Memory Manager -- Testing...\n")

    initialize_memory()

    sid = generate_session_id()
    print(f"  Generated session ID: {sid}")

    save_message(sid, "user", "hello")
    save_message(sid, "assistant", "Hi there! How can I help you?")
    save_message(sid, "user", "what is AI?")
    save_message(sid, "assistant", "AI is the simulation of human intelligence by machines.")
    print(f"  Saved 4 test messages to {sid}")

    messages = load_session_messages(sid)
    print(f"\n  Loaded {len(messages)} messages:")
    for msg in messages:
        print(f"    {msg['role']:>10}: {msg['content']}")

    # Test the new tables and helpers
    print("\n  --- Testing Interactions & Embeddings ---")
    int_id = save_interaction(sid, "I want to become a CEO", "That is a great career goal!", 0.95)
    print(f"  Saved interaction to DB, ID: {int_id}")
    
    test_embedding = [0.1, -0.2, 0.3, 0.4]
    save_embedding("interactions", int_id, "I want to become a CEO", test_embedding)
    print("  Saved embedding to DB.")

    loaded = load_embeddings("interactions")
    print(f"  Loaded {len(loaded)} embeddings:")
    for item in loaded:
        print(f"    ID: {item['id']}, Table: {item['source_table']}, Source ID: {item['source_id']}")
        print(f"    Content: '{item['content_text']}'")
        print(f"    Vector: {item['embedding']}")

    print(f"\n  Last session: {get_last_session_id()}")
    print(f"  Done! Database: {DB_PATH}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINT 8 — ACTION LOG
# ═══════════════════════════════════════════════════════════════════════════════

def log_action(session_id: str, action_type: str, target: str,
               coords_x: int | None = None, coords_y: int | None = None,
               success: bool = False, verified: bool = False,
               error_msg: str | None = None) -> int:
    """
    Logs an action PANDA took (click, type, press, scroll, drag, browser_*).
    Returns the action_log row ID.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    created_at = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO action_log (session_id, action_type, target, coords_x, coords_y,
                                success, verified, error_msg, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, action_type, target, coords_x, coords_y,
          1 if success else 0, 1 if verified else 0, error_msg, created_at))

    action_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return action_id


def get_recent_actions(session_id: str, limit: int = 10) -> list[dict]:
    """Returns the N most recent actions for a session."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM action_log
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (session_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_trajectory(goal: str, steps_json: str, status: str, summary: str = None) -> int:
    """Saves a task execution trajectory (steps and outcome) to the DB."""
    conn = _get_connection()
    cursor = conn.cursor()
    created_at = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO task_trajectories (goal, steps_json, status, summary, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (goal, steps_json, status, summary, created_at))
    trajectory_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trajectory_id


def load_trajectory_by_id(trajectory_id: int) -> dict | None:
    """Loads a specific task trajectory by its ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM task_trajectories WHERE id = ?
    """, (trajectory_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_todo(task: str, deadline: str = None, reminder_minutes_before: int = 15, done: int = 0, created_at: str = None) -> int:
    """Saves a todo task to the todos table in the DB. Returns the new todo's ID."""
    conn = _get_connection()
    cursor = conn.cursor()
    if not created_at:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO todos (task, done, created_at, deadline, reminder_minutes_before, reminded)
        VALUES (?, ?, ?, ?, ?, 0)
    """, (task, done, created_at, deadline, reminder_minutes_before))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def load_all_todos(include_done: bool = True) -> list:
    """Loads all todos from the DB."""
    conn = _get_connection()
    cursor = conn.cursor()
    if include_done:
        cursor.execute("SELECT * FROM todos ORDER BY id ASC")
    else:
        cursor.execute("SELECT * FROM todos WHERE done = 0 ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def complete_todo_db(todo_id: int) -> bool:
    """Marks a todo as done (1). Returns True if updated."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def remove_todo_db(todo_id: int) -> bool:
    """Removes a todo from the DB. Returns True if deleted."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def clear_completed_todos_db() -> int:
    """Deletes all completed (done = 1) todos. Returns count of deleted."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM todos WHERE done = 1")
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count


def get_upcoming_deadlines() -> list:
    """
    Returns a list of todos that are due soon, based on reminder_minutes_before,
    and haven't been reminded yet.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM todos WHERE done = 0 AND reminded = 0 AND deadline IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()

    upcoming = []
    now = datetime.now()
    for row in rows:
        todo = dict(row)
        deadline_str = todo["deadline"]
        reminder_mins = todo["reminder_minutes_before"]
        
        dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(deadline_str, fmt)
                break
            except ValueError:
                pass
        
        if dt:
            trigger_time = dt - timedelta(minutes=reminder_mins)
            if now >= trigger_time:
                upcoming.append(todo)
                
    return upcoming


def mark_todo_reminded(todo_id: int):
    """Sets reminded = 1 to prevent duplicate reminders."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE todos SET reminded = 1 WHERE id = ?", (todo_id,))
    conn.commit()
    conn.close()

