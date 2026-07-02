"""
✨ PANDA — Memory  (merged module, Mark V)
==========================================
Single source of truth for everything PANDA remembers.

Two classes, two responsibilities — cleanly separated inside one file:

  PandaMemory        — persistent stats, achievements, gamification, welcome
                       messages, command tracking, slot-filling state.
                       Backed by: data/memory.json

  ConversationManager — SQLite-backed conversation history, session IDs,
                        token trimming, content filtering, startup restoration.
                        Backed by: memory/panda_memory.db (via memory_manager.py)

Why merged?
  The old split (memory.py + conversation_manager.py) caused both classes to
  maintain parallel conversation lists that drifted out of sync. alya.py had to
  call both memory.add_to_conversation() AND conv_manager.save_turn() on every
  single reply — double-writing, double risk of inconsistency.

  Now: PandaMemory owns stats/gamification. ConversationManager owns conversation.
  alya.py calls conv_manager.save_turn() once. Done.

Architecture rule:
  alya.py  →  PandaMemory        (stats, achievements, pending slot state)
  alya.py  →  ConversationManager (context for LLM, conversation persistence)
           →  memory_manager.py  →  SQLite

What you're learning:
  - Merging modules without breaking callers (backward-compat discipline)
  - Separation of concerns inside a single file
  - Why data duplication is a bug waiting to happen
"""

import json
import os
import re
import datetime

import memory_core.memory_manager as memory_manager


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — PANDA MEMORY  (stats · achievements · gamification)
# ═══════════════════════════════════════════════════════════════════════════════

# ─── File path ────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_HERE, "data")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")


# ─── Achievements ─────────────────────────────────────────────────────────────

ACHIEVEMENTS = {
    "first_boot": {
        "name": "🏁 First Boot",
        "description": "Started PANDA for the first time",
        "condition": lambda mem: mem["total_sessions"] >= 1,
    },
    "regular_user": {
        "name": "🔄 Regular User",
        "description": "Used PANDA 5 times",
        "condition": lambda mem: mem["total_sessions"] >= 5,
    },
    "power_user": {
        "name": "⚡ Power User",
        "description": "Used PANDA 25 times",
        "condition": lambda mem: mem["total_sessions"] >= 25,
    },
    "veteran": {
        "name": "🎖️ Veteran",
        "description": "Used PANDA 100 times",
        "condition": lambda mem: mem["total_sessions"] >= 100,
    },
    "chatterbox": {
        "name": "💬 Chatterbox",
        "description": "Sent 50 commands in total",
        "condition": lambda mem: mem["total_commands"] >= 50,
    },
    "marathon_talker": {
        "name": "🏃 Marathon Talker",
        "description": "Sent 500 commands in total",
        "condition": lambda mem: mem["total_commands"] >= 500,
    },
    "early_bird": {
        "name": "🐦 Early Bird",
        "description": "Used PANDA before 7 AM",
        "condition": lambda mem: mem.get("used_early", False),
    },
    "night_owl": {
        "name": "🦉 Night Owl",
        "description": "Used PANDA after midnight",
        "condition": lambda mem: mem.get("used_late", False),
    },
    "todo_master": {
        "name": "📋 To-Do Master",
        "description": "Completed 10 tasks",
        "condition": lambda mem: mem.get("todos_completed", 0) >= 10,
    },
    "joker": {
        "name": "🃏 Joker",
        "description": "Asked for 10 jokes",
        "condition": lambda mem: mem.get("jokes_heard", 0) >= 10,
    },
}


class PandaMemory:
    """
    Manages PANDA's persistent stats, gamification, and short-term slot state.

    What lives here:
      - Session count and timestamps
      - Command frequency tracking and favorites
      - Achievement system (gamification)
      - Welcome message generation (time-away calculation)
      - data["pending"] — slot-filling state for multi-turn intent flows

    What does NOT live here (moved to ConversationManager):
      - Conversation history (was double-writing; SQLite version is authoritative)

    Backed by: data/memory.json
    """

    def __init__(self):
        self._ensure_data_dir()
        self.data = self._load()
        # Snapshot BEFORE _start_session overwrites last_session — needed for
        # get_welcome_message() to calculate how long the user was away.
        self._previous_last_session = self.data.get("last_session")
        self._start_session()

    def _ensure_data_dir(self):
        os.makedirs(DATA_DIR, exist_ok=True)

    def _load(self):
        """
        Loads memory from disk, or creates a fresh default on first boot.

        What you're learning:
        - JSON file as persistent storage (same concept as MongoDB/Firebase)
        - Defensive defaults — always have safe values on first run
        """
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r") as f:
                    data = json.load(f)
                # Back-compat: strip legacy "conversation" key if present —
                # SQLite is now the single source of truth for that.
                data.pop("conversation", None)
                return data
            except (json.JSONDecodeError, IOError):
                pass

        return {
            "user_name":            "Aryan",
            "total_sessions":       0,
            "total_commands":       0,
            "first_session":        None,
            "last_session":         None,
            "command_counts":       {},
            "achievements_unlocked":[],
            "todos_completed":      0,
            "jokes_heard":          0,
            "facts_heard":          0,
            "used_early":           False,
            "used_late":            False,
            "favorite_commands":    [],
            # Short-term slot-filling state (NOT conversation history).
            # alya.py sets this to track half-finished intent flows, e.g.
            # {"intent": "reminder", "task": "drink water", "time": None}
            "pending":              None,
        }

    def _save(self):
        """Saves memory to disk."""
        self._ensure_data_dir()
        with open(MEMORY_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def _start_session(self):
        """
        Updates session counters and time-based achievement flags.
        Called automatically in __init__.
        """
        now = datetime.datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        self.data["total_sessions"] += 1

        if not self.data["first_session"]:
            self.data["first_session"] = now_str

        hour = now.hour
        if hour < 7:
            self.data["used_early"] = True
        if hour >= 23 or hour < 5:
            self.data["used_late"] = True

        self.data["last_session"] = now_str
        self._save()

    # ── Command tracking ──────────────────────────────────────────────────────

    def record_command(self, command: str):
        """
        Records that a command was used — for stats and favorites tracking.

        What you're learning:
        - Counting occurrences with dictionaries
        - Sorting to find top-N items
        - This is the basis of analytics systems (Google Analytics, Mixpanel)
        """
        self.data["total_commands"] += 1

        counts = self.data["command_counts"]
        counts[command] = counts.get(command, 0) + 1

        sorted_cmds = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        self.data["favorite_commands"] = [cmd for cmd, _ in sorted_cmds[:5]]

        self._save()

    def record_todo_completed(self):
        self.data["todos_completed"] = self.data.get("todos_completed", 0) + 1
        self._save()

    def record_joke(self):
        self.data["jokes_heard"] = self.data.get("jokes_heard", 0) + 1
        self._save()

    def record_fact(self):
        self.data["facts_heard"] = self.data.get("facts_heard", 0) + 1
        self._save()

    # ── Welcome message ───────────────────────────────────────────────────────

    def get_welcome_message(self) -> str:
        """
        Generates a personalised welcome message with time-away info.

        Uses self._previous_last_session (snapshotted in __init__ before
        _start_session overwrote it) so the time delta is accurate.

        What you're learning:
        - Datetime arithmetic — calculating time differences
        - Conditional personalisation — adapting messages to context
        """
        name     = self.data["user_name"]
        sessions = self.data["total_sessions"]

        if sessions == 1:
            return f"  Welcome, {name}! This is our first session together! Let's go! 🚀"

        if not self._previous_last_session:
            return f"  Welcome back, {name}! Session #{sessions}!"

        try:
            last  = datetime.datetime.strptime(
                self._previous_last_session, "%Y-%m-%d %H:%M:%S"
            )
            delta         = datetime.datetime.now() - last
            total_seconds = int(delta.total_seconds())

            if total_seconds < 60:
                time_away = "just a moment"
            elif total_seconds < 3600:
                time_away = f"{total_seconds // 60} minutes"
            elif delta.days == 0:
                time_away = f"{total_seconds // 3600} hours"
            elif delta.days == 1:
                time_away = "a day"
            else:
                time_away = f"{delta.days} days"

            return (
                f"  Welcome back, {name}! You were away for {time_away}. "
                f"Session #{sessions}!"
            )
        except (ValueError, KeyError):
            return f"  Welcome back, {name}! Session #{sessions}!"

    # ── Achievements ──────────────────────────────────────────────────────────

    def check_achievements(self) -> list:
        """
        Checks all achievement conditions and returns a list of newly
        unlocked achievement messages (strings).

        What you're learning:
        - Gamification — tracking milestones to reward engagement
        - Lambda functions used as condition predicates
        """
        new_achievements = []

        for ach_id, ach_data in ACHIEVEMENTS.items():
            if ach_id in self.data["achievements_unlocked"]:
                continue
            try:
                if ach_data["condition"](self.data):
                    self.data["achievements_unlocked"].append(ach_id)
                    new_achievements.append(
                        f"  🏆 Achievement Unlocked: {ach_data['name']}\n"
                        f"     {ach_data['description']}"
                    )
            except (KeyError, TypeError):
                continue

        if new_achievements:
            self._save()

        return new_achievements

    # ── Stats dashboard ───────────────────────────────────────────────────────

    def get_stats(self) -> str:
        data = self.data

        lines = [
            "╔══════════════════════════════════════╗",
            "║        📊  YOUR PANDA STATS           ║",
            "╚══════════════════════════════════════╝",
            "",
            f"  👤 User: {data['user_name']}",
            f"  🔄 Total Sessions: {data['total_sessions']}",
            f"  💬 Total Commands: {data['total_commands']}",
        ]

        if data.get("first_session"):
            lines.append(f"  📅 First Session: {data['first_session']}")

        if data.get("favorite_commands"):
            lines += ["", "  ⭐ Your Top Commands:"]
            counts = data["command_counts"]
            for cmd in data["favorite_commands"][:5]:
                lines.append(f"     • {cmd} ({counts.get(cmd, 0)}x)")

        unlocked = data.get("achievements_unlocked", [])
        lines += ["", f"  🏆 Achievements: {len(unlocked)}/{len(ACHIEVEMENTS)}"]

        for ach_id in unlocked:
            if ach_id in ACHIEVEMENTS:
                lines.append(f"     {ACHIEVEMENTS[ach_id]['name']}")

        locked = [a for a in ACHIEVEMENTS if a not in unlocked]
        if locked:
            lines += ["", "  🔒 Locked Achievements:"]
            for ach_id in locked[:3]:
                lines.append(f"     ??? — {ACHIEVEMENTS[ach_id]['description']}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — CONVERSATION MANAGER  (SQLite conversation · sessions · trimming)
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_CONTEXT_MESSAGES = 20   # 10 full turns (user + assistant)
MAX_CONTEXT_TOKENS       = 4000 # tokens reserved for conversation history
CHARS_PER_TOKEN          = 4    # rough estimate: 1 token ≈ 4 English characters
MIN_CONTENT_LENGTH       = 2    # skip blank / single-char messages

# ─── Content filter ───────────────────────────────────────────────────────────

_NOISE_PATTERNS = [
    r"^\s*$",       # blank / whitespace only
    r"^\[DEBUG\]",  # debug logs
    r"^\[ERROR\]",  # error logs
    r"^\[TOOL\]",   # tool execution logs
    r"^SYSTEM:",    # system messages
    r"^_{5,}$",     # separator lines (_____)
    r"^={5,}$",     # separator lines (=====)
    r"^-{5,}$",     # separator lines (-----)
]
_NOISE_REGEX = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)


def _is_valid_content(content: str) -> bool:
    """
    Returns True only for real conversational content worth saving.

    Rejects blank messages, one-char inputs, system logs, separator lines.
    Dirty memory = confused LLM. Filter before storage, not after.

    What you're learning:
    - Data quality — garbage in, garbage out applies to AI too
    - Guard clauses — reject bad input early
    """
    if not content or not content.strip():
        return False
    if len(content.strip()) < MIN_CONTENT_LENGTH:
        return False
    if _NOISE_REGEX.search(content.strip()):
        return False
    return True


# ─── Token estimation & trimming ─────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """
    Rough token count: ~4 chars = 1 token for English text.
    Good enough for sliding-window decisions. Use tiktoken for exact counts.
    """
    return max(1, len(text) // CHARS_PER_TOKEN)


def _estimate_messages_tokens(messages: list) -> int:
    total = 0
    for msg in messages:
        total += 4  # per-message overhead (role + formatting)
        total += _estimate_tokens(msg.get("content", ""))
    return total


def _trim_to_token_budget(
    messages: list,
    max_tokens: int = MAX_CONTEXT_TOKENS,
) -> list:
    """
    Drops the oldest messages until the list fits within max_tokens.
    Always preserves at least the last 2 messages (1 full turn).

    This is exactly what ChatGPT, Claude, and Gemini do internally on
    every single API call to manage their context windows.

    What you're learning:
    - Sliding-window with a token budget — the standard production approach
    - Why "the model forgot what I said" happens: the window filled up
    """
    if not messages:
        return messages
    while len(messages) > 2 and _estimate_messages_tokens(messages) > max_tokens:
        messages.pop(0)
    return messages


# ─── ConversationManager class ────────────────────────────────────────────────

class ConversationManager:
    """
    The AI's brain state layer — single source of truth for conversation.

    Responsibilities:
      Step 9  — Sequential session IDs  (session_1, session_2, …)
      Step 10 — Memory loading rules    (recent N messages only, never full DB)
      Step 11 — Token trimming          (estimate tokens, trim oldest)
      Step 12 — This class itself       (brain state orchestration)
      Step 13 — Startup restoration     (load last session for warm greeting)
      Step 14 — Content filtering       (blanks, noise, debug output)

    Architecture:
      alya.py  →  ConversationManager  →  memory_manager.py  →  SQLite

    Usage:
        conv = ConversationManager()
        conv.initialize()                    # DB setup + session ID + restoration
        context = conv.get_context()         # load + trim → Ollama-ready list
        conv.save_turn(user_input, reply)    # filter + save both sides

    What you're learning:
    - Facade pattern — a clean interface that hides complex subsystems
    - This is EXACTLY what ChatGPT, Claude, and Gemini do internally:
      a manager class that decides what the model sees each turn
    """

    def __init__(self):
        self.session_id: str          = ""
        self.prev_session_id: str     = ""
        self._last_session_summary: str = ""

    # ── Initialization ────────────────────────────────────────────────────────

    def initialize(self):
        """
        Called once when PANDA starts. Runs in order:
          1. Creates/opens the SQLite database
          2. Generates a new sequential session ID
          3. Loads the previous session for context restoration
        """
        memory_manager.initialize_memory()
        self.session_id = memory_manager.generate_session_id()
        self.prev_session_id = memory_manager.get_last_session_id() or ""
        self._load_last_session_context()

        print(f"  [ConvManager] Session: {self.session_id}")
        if self._last_session_summary:
            print("  [ConvManager] Previous session loaded for context.")

    # ── Startup restoration (Step 13) ─────────────────────────────────────────

    def _load_last_session_context(self):
        """
        Loads a summary of the most recent previous session so PANDA can say
        "Last time we were discussing…" at startup.

        What you're learning:
        - State restoration — how apps resume where you left off
        - This mirrors the "Continue conversation" feature in ChatGPT
        """
        last_sid = self.prev_session_id

        if not last_sid or last_sid == self.session_id:
            self._last_session_summary = ""
            return

        old_messages = memory_manager.get_session_summary(last_sid, limit=6)

        if not old_messages:
            self._last_session_summary = ""
            return

        user_topics = [
            msg["content"][:80]
            for msg in old_messages
            if msg["role"] == "user"
        ]

        if user_topics:
            topics_text = "; ".join(user_topics[:3])
            self._last_session_summary = (
                f"Last session ({last_sid}), the user was discussing: {topics_text}"
            )
        else:
            self._last_session_summary = ""

    def get_startup_context(self) -> str:
        """
        Returns a human-readable summary of the last session.
        Empty string if this is the first session or the DB is empty.
        """
        return self._last_session_summary

    # ── Context building (Steps 10 + 11) ─────────────────────────────────────

    def get_context(self, limit: int = DEFAULT_CONTEXT_MESSAGES) -> list:
        """
        Returns the conversation history ready to pass directly to Ollama,
        with token trimming applied.

        Pipeline:
          1. Load the most recent N messages from SQLite  (Step 10)
          2. Trim to stay within MAX_CONTEXT_TOKENS        (Step 11)
          3. Return [{"role": "...", "content": "..."}, …]

        What you're learning:
        - Context window management — the hardest part of LLM application design
        - Why loading the ENTIRE database would be catastrophic:
            * Exceeds token limits → API error or silent truncation
            * Old context confuses the LLM with stale information
            * Response quality degrades as context noise grows
        """
        messages = memory_manager.load_session_messages(
            self.session_id, limit=limit
        )

        # Cross-session continuity: if the current session is brand new (0 messages),
        # preload the previous session's messages to bootstrap context restoration.
        if len(messages) == 0 and hasattr(self, "prev_session_id") and self.prev_session_id:
            messages = memory_manager.load_session_messages(
                self.prev_session_id, limit=limit
            )

        return _trim_to_token_budget(messages)

    # ── Save turn (Steps 8 + 14) ──────────────────────────────────────────────

    def save_turn(self, user_input: str, assistant_reply: str):
        """
        Saves one full conversation turn (user + assistant) to SQLite.

        Step 14 content filtering is applied BEFORE saving:
          - Blank or whitespace-only messages are skipped
          - System logs, debug output, separator lines are skipped
          - Only real conversational content reaches the database

        This is the ONLY place that writes conversation to storage.
        Never call memory_manager.save_message() directly from alya.py.

        What you're learning:
        - Filter before storage, not after — cheaper and safer
        - In production you'd also strip PII and profanity here
        """
        if _is_valid_content(user_input):
            memory_manager.save_message(self.session_id, "user", user_input)
        if _is_valid_content(assistant_reply):
            memory_manager.save_message(self.session_id, "assistant", assistant_reply)

        # Background semantic memory saving (Sprint 1)
        if _is_valid_content(user_input) and _is_valid_content(assistant_reply):
            import threading
            import memory_core.vector_memory as vector_memory
            threading.Thread(
                target=vector_memory.save_turn_semantic,
                args=(self.session_id, user_input, assistant_reply),
                daemon=True
            ).start()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_session_id(self) -> str:
        """Returns the current session ID, e.g. 'session_42'."""
        return self.session_id


# ═══════════════════════════════════════════════════════════════════════════════
# QUICK SELF-TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n  PANDA Memory (merged) — self-test\n")

    panda = PandaMemory()
    print(panda.get_welcome_message())

    conv = ConversationManager()
    conv.initialize()
    conv.save_turn("hello", "Hi! How can I help?")
    conv.save_turn("what is machine learning?", "ML is a subset of AI…")
    conv.save_turn("", "")           # filtered — blank
    conv.save_turn("[DEBUG] x", "y") # filtered — debug noise

    ctx = conv.get_context()
    print(f"\n  Context ({len(ctx)} messages):")
    for m in ctx:
        print(f"    {m['role']:>10}: {m['content'][:60]}")

    print(f"\n  Session: {conv.get_session_id()}")
    print(f"  Startup: {conv.get_startup_context() or '(first session)'}")

    panda.record_command("llm_chat")
    new_ach = panda.check_achievements()
    for a in new_ach:
        print(f"\n{a}")

    print("\n  Done!\n")