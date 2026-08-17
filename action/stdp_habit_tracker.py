"""
PANDA — STDP Habit Tracker (Experimental)
===========================================
A lightweight Spiking Neural Network (SNN) that learns repeating
action sequences using Spike-Timing-Dependent Plasticity (STDP).

How it works:
  1. Every user action (click, type, window switch) is mapped to a
     unique "neuron" with an integer ID.
  2. When an action occurs, its neuron "fires" a spike at time t.
  3. A synapse weight matrix W tracks connection strengths between
     all neuron pairs.
  4. STDP Rule:
     - If neuron A fires BEFORE neuron B (causal), W[A,B] increases.
     - If neuron A fires AFTER neuron B (non-causal), W[A,B] decreases.
  5. After enough repetitions, strong weights reveal habitual sequences.
     When neuron A fires, we check W[A,:] for strong connections to
     predict the likely next action.

Built by Aryan — PANDA Experimental SNN Sprint
"""

import time
import json
import os
import threading
import numpy as np


# ── STDP Hyperparameters ─────────────────────────────────────────────────────

# Learning rates
A_PLUS = 0.05       # Potentiation amplitude (causal: A fires before B)
A_MINUS = 0.025     # Depression amplitude (anti-causal: A fires after B)

# Time constants (in seconds)
TAU_PLUS = 10.0     # Window for potentiation (10 seconds)
TAU_MINUS = 10.0    # Window for depression (10 seconds)

# Prediction threshold
PREDICTION_THRESHOLD = 0.35

# Maximum number of neurons (dynamic, but capped for memory safety)
MAX_NEURONS = 256

# Spike history window size
SPIKE_HISTORY_SIZE = 20

# Persistence file path
_WEIGHTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
_WEIGHTS_FILE = os.path.join(_WEIGHTS_DIR, "stdp_weights.json")


# ── Internal State ───────────────────────────────────────────────────────────

_lock = threading.Lock()

# Event registry: maps event string -> neuron ID
_event_to_id: dict[str, int] = {}
_id_to_event: dict[int, str] = {}
_next_neuron_id: int = 0

# Synapse weight matrix (N x N), initialized lazily
_weights: np.ndarray | None = None

# Spike history: list of (neuron_id, timestamp)
_spike_history: list[tuple[int, float]] = []

# Track whether we have unsaved changes
_dirty = False


# ── Neuron Registration ──────────────────────────────────────────────────────

def _get_or_create_neuron(event_name: str) -> int:
    """
    Maps an event string to a unique neuron ID.
    Creates a new neuron if the event hasn't been seen before.
    Automatically expands the weight matrix when new neurons are added.
    """
    global _next_neuron_id, _weights, _dirty

    if event_name in _event_to_id:
        return _event_to_id[event_name]

    if _next_neuron_id >= MAX_NEURONS:
        # Recycle: don't create new neurons beyond the cap
        # Find the least-used neuron and overwrite it
        return _next_neuron_id - 1

    neuron_id = _next_neuron_id
    _event_to_id[event_name] = neuron_id
    _id_to_event[neuron_id] = event_name
    _next_neuron_id += 1

    # Expand the weight matrix
    if _weights is None:
        _weights = np.zeros((MAX_NEURONS, MAX_NEURONS), dtype=np.float32)
    
    _dirty = True
    return neuron_id


# ── STDP Learning ────────────────────────────────────────────────────────────

def _apply_stdp(new_neuron_id: int, spike_time: float):
    """
    Applies the STDP learning rule:
    For each previous spike i in the history, updates the synapse
    weight between neuron i and the new neuron j based on their
    temporal ordering.

    Causal (i fires before j):   W[i,j] += A+ * exp(-Δt / τ+)
    Anti-causal (j fires before i): W[i,j] -= A- * exp(Δt / τ-)
    """
    global _weights, _dirty

    if _weights is None:
        return

    for prev_id, prev_time in _spike_history:
        if prev_id == new_neuron_id:
            continue  # Skip self-connections

        dt = spike_time - prev_time

        if 0 < dt < TAU_PLUS * 3:
            # Causal: prev fired BEFORE new → strengthen prev→new
            dw = A_PLUS * np.exp(-dt / TAU_PLUS)
            _weights[prev_id, new_neuron_id] = min(
                1.0, _weights[prev_id, new_neuron_id] + dw
            )
            _dirty = True

        elif -TAU_MINUS * 3 < dt < 0:
            # Anti-causal: prev fired AFTER new → weaken prev→new
            dw = A_MINUS * np.exp(dt / TAU_MINUS)
            _weights[prev_id, new_neuron_id] = max(
                0.0, _weights[prev_id, new_neuron_id] - dw
            )
            _dirty = True


# ── Public API ───────────────────────────────────────────────────────────────

def register_event(event_name: str):
    """
    Registers a user action event. This:
    1. Maps the event to a neuron (creating one if new).
    2. Records the spike timestamp.
    3. Applies STDP learning against all recent spikes.

    Call this from screen_monitor.py whenever a click, type,
    or window switch event occurs.

    Args:
        event_name: A categorized string like "window:Brave",
                    "type:youtube.com", "click:Search", "key:enter"
    """
    with _lock:
        neuron_id = _get_or_create_neuron(event_name)
        spike_time = time.time()

        # Apply STDP against history
        _apply_stdp(neuron_id, spike_time)

        # Record this spike
        _spike_history.append((neuron_id, spike_time))

        # Trim history to sliding window
        if len(_spike_history) > SPIKE_HISTORY_SIZE:
            _spike_history.pop(0)


def get_predictions(current_event: str | None = None, top_k: int = 3) -> list[dict]:
    """
    Returns the top-k predicted next actions based on learned habits.

    If current_event is provided, predictions are based on that neuron's
    outgoing weights. Otherwise, uses the most recent spike.

    Returns a list of dicts:
      [
        {"event": "type:youtube.com", "confidence": 0.82},
        {"event": "key:enter", "confidence": 0.71},
      ]
    """
    with _lock:
        if _weights is None or _next_neuron_id == 0:
            return []

        # Determine the source neuron
        source_id = None
        if current_event and current_event in _event_to_id:
            source_id = _event_to_id[current_event]
        elif _spike_history:
            source_id = _spike_history[-1][0]

        if source_id is None:
            return []

        # Get the outgoing weights from this neuron
        row = _weights[source_id, :_next_neuron_id]

        # Find indices above threshold
        candidates = []
        for j in range(len(row)):
            if row[j] >= PREDICTION_THRESHOLD and j != source_id:
                event_name = _id_to_event.get(j, f"unknown_{j}")
                candidates.append({
                    "event": event_name,
                    "confidence": round(float(row[j]), 3)
                })

        # Sort by confidence descending, return top_k
        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        return candidates[:top_k]


def get_habit_summary() -> str:
    """
    Returns a human-readable summary of learned habits for
    injection into the Actor LLM prompt.

    Returns empty string if no strong habits exist.
    """
    with _lock:
        if _weights is None or _next_neuron_id < 2:
            return ""

        # Find all strong connections
        strong_habits = []
        for i in range(_next_neuron_id):
            for j in range(_next_neuron_id):
                if i != j and _weights[i, j] >= PREDICTION_THRESHOLD:
                    src = _id_to_event.get(i, f"neuron_{i}")
                    dst = _id_to_event.get(j, f"neuron_{j}")
                    weight = float(_weights[i, j])
                    strong_habits.append((src, dst, weight))

        if not strong_habits:
            return ""

        # Sort by weight descending
        strong_habits.sort(key=lambda x: x[2], reverse=True)

        # Format top 5 habits
        lines = ["HABIT PATTERNS (learned from your behavior):"]
        for src, dst, weight in strong_habits[:5]:
            confidence_pct = int(weight * 100)
            lines.append(f"  - After '{src}', you usually do '{dst}' ({confidence_pct}% confidence)")

        return "\n".join(lines)


# ── Persistence ──────────────────────────────────────────────────────────────

def save_weights():
    """Saves the current synapse weights and event registry to disk."""
    global _dirty

    with _lock:
        if not _dirty or _weights is None:
            return

        os.makedirs(_WEIGHTS_DIR, exist_ok=True)

        data = {
            "event_to_id": _event_to_id,
            "id_to_event": {str(k): v for k, v in _id_to_event.items()},
            "next_neuron_id": _next_neuron_id,
            "weights": _weights[:_next_neuron_id, :_next_neuron_id].tolist()
        }

        try:
            with open(_WEIGHTS_FILE, "w") as f:
                json.dump(data, f, indent=2)
            _dirty = False
            print(f"  [STDP] Saved {_next_neuron_id} neurons to {_WEIGHTS_FILE}")
        except Exception as e:
            print(f"  [STDP] Error saving weights: {e}")


def load_weights():
    """Loads synapse weights and event registry from disk (if available)."""
    global _event_to_id, _id_to_event, _next_neuron_id, _weights, _dirty

    with _lock:
        if not os.path.exists(_WEIGHTS_FILE):
            print("  [STDP] No saved weights found. Starting fresh.")
            _weights = np.zeros((MAX_NEURONS, MAX_NEURONS), dtype=np.float32)
            return

        try:
            with open(_WEIGHTS_FILE, "r") as f:
                data = json.load(f)

            _event_to_id = data.get("event_to_id", {})
            _id_to_event = {int(k): v for k, v in data.get("id_to_event", {}).items()}
            _next_neuron_id = data.get("next_neuron_id", 0)

            saved_weights = data.get("weights", [])
            _weights = np.zeros((MAX_NEURONS, MAX_NEURONS), dtype=np.float32)
            n = min(len(saved_weights), MAX_NEURONS)
            for i in range(n):
                for j in range(min(len(saved_weights[i]), MAX_NEURONS)):
                    _weights[i, j] = saved_weights[i][j]

            _dirty = False
            print(f"  [STDP] Loaded {_next_neuron_id} neurons from disk.")
        except Exception as e:
            print(f"  [STDP] Error loading weights: {e}")
            _weights = np.zeros((MAX_NEURONS, MAX_NEURONS), dtype=np.float32)


def get_stats() -> dict:
    """Returns diagnostic statistics about the STDP network."""
    with _lock:
        if _weights is None:
            return {"neurons": 0, "strong_connections": 0, "spikes_in_history": 0}

        strong = int(np.sum(_weights[:_next_neuron_id, :_next_neuron_id] >= PREDICTION_THRESHOLD))
        return {
            "neurons": _next_neuron_id,
            "strong_connections": strong,
            "spikes_in_history": len(_spike_history),
            "total_events_registered": len(_event_to_id)
        }
