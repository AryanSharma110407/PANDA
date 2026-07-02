"""
PANDA — Fusion Layer
===================================================
Decision layer between intent + entities and execution.

Mark I was a single function with a chain of if/else checks — it could
only handle one shot at a time.  The moment a slot was missing the
conversation stalled because there was no memory of what was being built.

Mark II replaces that with a proper Finite State Machine (FSM).

                ┌──────────────────────────────────────────┐
                │           State Transition Map           │
                └──────────────────────────────────────────┘

      ┌─────────┐   intent received    ┌───────────────────┐
      │  IDLE   │─────────────────────▶│  AWAITING_SLOT    │
      │         │   (slots missing)    │  (partial data)   │
      └─────────┘                      └───────────────────┘
           │                                    │
           │  all slots present                 │  user fills missing slot(s)
           ▼                                    ▼
      ┌─────────┐◀───────────────────────────────
      │EXECUTING│   action dispatched → reset to IDLE
      └─────────┘

States
------
  IDLE            No active intent.  Waiting for a fresh command.
  AWAITING_SLOT   Intent known, but one or more required slots are missing.
                  Every user turn in this state tries to fill the gap.
  EXECUTING       All slots filled.  The payload is returned to alya.py
                  and the machine immediately resets to IDLE.

Public API (backward-compatible with Mark I)
--------------------------------------------
  fuse(intent, entities, user_input) → dict
      Drop-in replacement for the old function.  Internally delegates to
      the module-level FusionStateMachine singleton.

  get_state() → str
      Returns the current state name: "idle" | "awaiting_slot" | "executing"

  cancel() → dict
      Aborts any in-progress intent and returns to IDLE.

What you're learning here
--------------------------
- Finite State Machines — the backbone of parsers, game AI, networking
  protocols, and every agentic framework (LangGraph, AutoGPT, etc.)
- Singleton pattern — one shared instance manages all state
- Slot-filling dialogue management — the standard technique used by
  Alexa, Google Assistant, and Rasa for multi-turn NLU
- Enum — safer than raw strings for state names (typos become errors)
- Defensive merge — only overwrite a slot if the new value is truthy,
  so a follow-up "remind me to study" doesn't wipe out a previously
  captured time.
"""

from __future__ import annotations
from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════════
# STATE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

class State(Enum):
    """
    The three states of PANDA's dialogue manager.

    Using an Enum instead of plain strings means:
      - Invalid state names raise an AttributeError immediately (fast failure)
      - IDE auto-complete works
      - You can't accidentally assign State.IDLE = "typo"
    """
    IDLE          = "idle"
    AWAITING_SLOT = "awaiting_slot"
    EXECUTING     = "executing"


# ═══════════════════════════════════════════════════════════════════════════════
# SLOT SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

# Maps each intent → the slots it needs and what to ask when each is missing.
# Add a new intent here and the state machine handles it automatically.
#
# Format:
#   "intent_name": {
#       "slot_name": "question to ask the user if this slot is missing",
#   }
_SLOT_SCHEMAS: dict[str, dict[str, str]] = {
    "reminder": {
        "time": "When should I remind you?",
        "task": "What should I remind you to do?",
    },
    "goal_add": {
        "goal": "What is the goal you would like to add?",
    },
    "goal_complete": {
        "number": "Which goal number would you like to complete? (Use 'show goals' to see the list)",
    },
    "project_add": {
        "name": "What is the name of the project?",
        "description": "Can you give me a description of this project?",
    },
    "preference_add": {
        "preference": "What preference would you like to add?",
    },
    "correction_add": {
        "mistake": "What was the mistake in my memory?",
        "correction": "What is the correct information?",
    },
    "goal_plan": {
        "number": "Which goal number would you like to plan? (Use 'show goals' to see the list)",
    },
    "goal_progress": {
        "number": "Which goal number would you like to check progress on?",
    },
    "goal_next": {
        "number": "Which goal number would you like to see the next action for?",
    },
    "goal_priority": {
        "number": "Which goal number would you like to prioritize?",
        "priority": "What priority score (1-10) would you like to assign?",
    },
    "goal_replan": {
        "number": "Which goal number would you like to replan?",
    },
    "goal_pause": {
        "number": "Which goal number would you like to pause?",
    },
    "goal_abandon": {
        "number": "Which goal number would you like to abandon?",
    },
    "goal_history": {
        "number": "Which goal number would you like to view the history of?",
    },
    "goal_step_done": {
        "goal": "Which goal number does the step belong to?",
        "step": "Which step number would you like to mark as done?",
    },
    "goal_step_start": {
        "goal": "Which goal number does the step belong to?",
        "step": "Which step number would you like to start?",
    },
    "find": {
        "query": "What element would you like me to find on the screen?",
    },
    "click": {
        "target": "What would you like me to click?",
    },
    "type": {
        "text": "What would you like me to type?",
    },
    "press": {
        "key": "What key or key combination should I press?",
    },
    "scroll": {
        "direction": "Which direction should I scroll (up or down)?",
    },
    "drag": {
        "source": "Where should I start dragging from?",
        "target": "Where should I drag to?",
    },
    "browser_open": {
        "url": "What URL would you like me to open?",
    },
    "browser_search": {
        "query": "What would you like to search for?",
    },
    "browser_fill": {
        "selector": "What field should I fill?",
        "text": "What text should I type?",
    },
    "browser_click": {
        "selector": "What element should I click in the browser?",
    },
    "browser_scroll": {
        "direction": "Which direction should I scroll in the browser?",
    },
    "execute_task": {
        "task": "What task would you like me to execute autonomously?",
    },
}


# The set of all valid intent/action names that PANDA can execute.
VALID_INTENTS = {
    # Handled by handle_intent
    "greeting", "time", "date", "roadmap", "help",
    "open_app", "search", "youtube_search", "system_info", "screenshot",
    "folder", "apps_list", "sites_list", "weather", "news",
    "todo_add", "todo_show", "todo_done", "todo_remove", "todo_clear",
    "note_add", "notes_show", "notes_clear",
    "timer", "reminder", "schedule",
    "stats",
    "mood_bored", "mood_tired", "mood_stressed",
    "voice_on", "voice_off", "voice_in", "voice_out", "voice_status",
    "quit",
    # Handled by _execute_tool_action (Thinking Engine)
    "open_website", "search_google", "search_youtube", "get_system_info", "take_screenshot",
    "get_schedule", "save_note", "show_notes", "get_time", "get_date", "get_roadmap",
    "open_weather", "open_news",
    # Sprint 2 Intents
    "goal_add", "goal_show", "goal_complete", "project_add", "project_show",
    # Sprint 3 Intents
    "preference_add", "preference_show", "correction_add",
    # Sprint 5 Intents
    "reflect", "show_reflections",
    # Sprint 6 Intents
    "goal_plan", "goal_progress", "goal_step_done", "goal_step_start", "goal_next",
    "goal_priority", "goal_replan", "goal_pause", "goal_abandon", "goal_history",
    # Sprint 7 Intents
    "look", "look_text", "find", "describe_screen",
    # Sprint 8 Intents
    "click", "type", "press", "scroll", "drag", "browser_open", "browser_search", "browser_fill", "browser_click", "browser_scroll",
    # Sprint 9 Intents
    "execute_task",
    # History Intents
    "get_history", "show_history"
}


# ═══════════════════════════════════════════════════════════════════════════════
# STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════════════

class FusionStateMachine:
    """
    A slot-filling dialogue manager implemented as a Finite State Machine.

    Attributes
    ----------
    state           Current FSM state (State enum member).
    pending_intent  The intent being built up across turns.
    pending_slots   Accumulated entity data from all turns so far.
    missing_slots   Slots still needed before execution can proceed.
    """

    def __init__(self):
        self._reset()

    # ── Public interface ────────────────────────────────────────────────────

    def process(self, intent: str, entities: dict, user_input: str) -> dict:
        """
        Main entry point.  Called once per user turn.

        Routing:
          IDLE          → _from_idle()
          AWAITING_SLOT → _from_awaiting_slot()
          EXECUTING     → impossible (reset happens immediately after dispatch),
                          but guarded defensively just in case.
        """
        if self.state == State.IDLE:
            return self._from_idle(intent, entities)

        if self.state == State.AWAITING_SLOT:
            return self._from_awaiting_slot(intent, entities)

        # EXECUTING is a transient state — should never linger here,
        # but reset + reprocess rather than crashing.
        self._reset()
        return self._from_idle(intent, entities)

    def get_state(self) -> str:
        """Human-readable state name for alya.py / logging."""
        return self.state.value

    def cancel(self) -> dict:
        """
        User said 'cancel', 'never mind', etc.
        Clears all pending work and returns to IDLE.
        """
        intent = self.pending_intent or "action"
        self._reset()
        return {
            "status":  "cancelled",
            "message": f"Got it — I've cancelled the {intent}.",
        }

    # ── State handlers ──────────────────────────────────────────────────────

    def _from_idle(self, intent: str, entities: dict) -> dict:
        """
        IDLE: fresh command arrives.

        Steps:
          1. Store intent and whatever entities arrived.
          2. Validate — are all required slots present?
          3a. Missing slots → transition to AWAITING_SLOT, ask the question.
          3b. All slots present → transition through EXECUTING, dispatch.
        """
        if not intent or intent not in VALID_INTENTS:
            self._reset()
            return {
                "status": "error",
                "message": f"Sorry, I don't know how to perform the action '{intent}'.",
                "current_state": self.state.value,
            }

        self.pending_intent = intent
        # Defensive merge: only store truthy values
        self.pending_slots = {k: v for k, v in entities.items() if v}

        return self._advance()

    def _from_awaiting_slot(self, intent: str, entities: dict) -> dict:
        """
        AWAITING_SLOT: the user has replied to our follow-up question.

        We merge any new truthy entities into pending_slots — this is the
        'slot-filling' step — then re-validate and either ask again or execute.

        Note: we ignore the incoming `intent` here because the user is
        answering our question ('at 5 pm'), not issuing a new command.
        If they say something that parses as a completely new intent,
        alya.py's router should call cancel() first, then process() again.
        """
        for slot, value in entities.items():
            if value and slot not in self.pending_slots:
                self.pending_slots[slot] = value

        return self._advance()

    # ── Core validation + dispatch ──────────────────────────────────────────

    def _advance(self) -> dict:
        """
        Checks whether all required slots are filled.
        Transitions to AWAITING_SLOT or EXECUTING accordingly.
        """
        missing = self._find_missing_slots()

        if missing:
            # ── Transition: IDLE / AWAITING_SLOT → AWAITING_SLOT ──────────
            self.state        = State.AWAITING_SLOT
            self.missing_slots = missing

            # Ask about the first missing slot only — one question per turn
            # keeps the conversation natural.  The loop continues next turn.
            first_missing = missing[0]
            schema        = _SLOT_SCHEMAS.get(self.pending_intent, {})
            question      = schema.get(first_missing, "Can you give me more details?")

            return {
                "status":        "missing",
                "message":       question,
                "missing_slots": missing,
                "current_state": self.state.value,
            }

        # ── Transition: → EXECUTING → IDLE ────────────────────────────────
        self.state = State.EXECUTING
        result = {
            "status":        "ready",
            "action":        self.pending_intent,
            "data":          dict(self.pending_slots),
            "current_state": self.state.value,
        }
        self._reset()   # immediately return to IDLE after dispatching
        return result

    def _find_missing_slots(self) -> list[str]:
        """
        Returns a list of slot names that are required but not yet filled.
        For intents not in _SLOT_SCHEMAS, no slots are required → always [].
        """
        schema = _SLOT_SCHEMAS.get(self.pending_intent, {})
        return [slot for slot in schema if not self.pending_slots.get(slot)]

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _reset(self):
        """Returns the machine to a clean IDLE state."""
        self.state          = State.IDLE
        self.pending_intent = None
        self.pending_slots  = {}
        self.missing_slots  = []


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL SINGLETON  (backward-compatible public API)
# ═══════════════════════════════════════════════════════════════════════════════

# One shared instance per process.  alya.py imports this module once;
# every call to fuse() operates on the same machine, so state is preserved
# across conversation turns without alya.py knowing anything about FSMs.
_machine = FusionStateMachine()


def fuse(intent: str, entities: dict, user_input: str) -> dict:
    """
    Drop-in replacement for the Mark I fuse() function.

    alya.py calls this exactly as before:
        result = fuse(intent, entities, user_input)

    Internally it delegates to the singleton FusionStateMachine, which
    now remembers what happened last turn.
    """
    return _machine.process(intent, entities, user_input)


def get_state() -> str:
    """Returns the current FSM state: 'idle' | 'awaiting_slot' | 'executing'"""
    return _machine.get_state()


def cancel() -> dict:
    """Aborts any in-progress slot-filling and returns to IDLE."""
    return _machine.cancel()


def get_pending_intent() -> str | None:
    """
    Returns the intent currently being slot-filled, or None if idle.

    Used by alya.py's AWAITING_SLOT bypass so it can pass the right
    intent to extract_entities() before calling fuse() again.
    """
    return _machine.pending_intent