"""
PANDA Vision — Vision Tools
============================
High-level vision actions exposed to the PANDA agent.

Tool → Layer mapping:
  handle_look()           → Layer 1 (UIAuto active window) + Layer 2 (OCR) + Layer 3 (OpenCV structure)
  handle_look_text()      → Layer 2 (OCR full screen read)
  handle_find()           → Layer 1 → Layer 2 → None  (via element_registry)
  handle_describe_screen()→ Layer 1 + Layer 2 (LLM-summarised)

Built by Aryan — PANDA Vision Sprint 7+
"""

import json
import os

# Guard memory_manager import — if the SQLite DB is locked/corrupt the
# vision tools should still work; they just won't persist observations.
try:
    import memory_manager as memory_manager
    _MEMORY_AVAILABLE = True
except Exception as _mem_err:
    print(
        f"  \033[33m[VisionTools] memory_manager unavailable: {_mem_err}. "
        f"Screen observations will not be saved.\033[0m",
        flush=True
    )
    _MEMORY_AVAILABLE = False

    class _MemoryStub:
        """Minimal no-op stub so vision functions don't crash without a DB."""
        def get_recent_observations(self, *a, **kw):  return []
        def add_screen_observation(self, *a, **kw):    return None

    memory_manager = _MemoryStub()

from .screenshot_manager import save_debug_screenshot
from .ocr_engine import read_screen
from .element_registry import find_element_dynamic, list_known_elements
from .screen_state import build_screen_state


# ─── LLM Screen Summariser ────────────────────────────────────────────────────

# Noise keywords to filter from UI controls before sending to LLM.
# These are system tray / taskbar entries that aren't meaningful screen context.
_CONTROL_NOISE = {
    "show hidden icons", "taskbar", "start", "search", "task view",
    "notification", "notifications", "your device needs to restart",
    "select a time to restart", "up to date", "backed up and synced",
    "onedrive", "meet now", "cortana",
}

def _filter_controls(controls: list[str]) -> list[str]:
    """Remove obvious system tray / notification noise from UI control names."""
    out = []
    for c in controls:
        c_low = c.lower().strip()
        # Skip if it matches a known noise phrase or is just a symbol/single char
        if any(noise in c_low for noise in _CONTROL_NOISE):
            continue
        if len(c) <= 1:
            continue
        out.append(c)
    return out


def _summarise_screen_with_llm(state: dict) -> str | None:
    """
    Passes the raw screen state to the LLM (Ollama) and asks for a single
    natural-language sentence describing what's on the screen.

    Returns a string on success, None on any failure (caller uses fallback).
    """
    try:
        import ollama

        OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
        MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")

        active_window = state.get("active_window", "Unknown")

        # Top OCR texts (high-confidence only)
        ocr_items = sorted(
            state.get("visible_text", []),
            key=lambda x: x.get("confidence", 0),
            reverse=True
        )
        top_texts = [t["text"].strip() for t in ocr_items[:8] if t.get("text", "").strip()]

        # Filtered UI controls (no system tray noise)
        raw_controls = state.get("ui_controls", [])
        clean_controls = _filter_controls(raw_controls)[:6]

        # Structural summary (Layer 3)
        elements = state.get("detected_elements", [])
        btn_count = sum(1 for e in elements if e.get("type") == "button")
        panel_count = sum(1 for e in elements if e.get("type") == "window")

        # Build a compact data block for the LLM
        data_lines = [f"Active window: {active_window}"]
        if top_texts:
            data_lines.append(f"Visible text: {', '.join(top_texts)}")
        if clean_controls:
            data_lines.append(f"UI controls: {', '.join(clean_controls)}")
        if btn_count or panel_count:
            data_lines.append(
                f"Structure: ~{btn_count} buttons, ~{panel_count} panels detected"
            )

        prompt = (
            "You are PANDA, describing the screen in ONE natural conversational sentence.\n"
            "Focus on what the user is working on, ignoring system tray noise.\n"
            "Note that both UI Controls and Visible Text are equally valid targets that can be clicked or right-clicked.\n\n"
            "Screen data:\n" + "\n".join(data_lines) + "\n\n"
            "Output format: Reply with ONLY the sentence. No preamble, no labels."
        )

        client = ollama.Client(
            host=OLLAMA_URL,
            timeout=120.0,
            headers={"ngrok-skip-browser-warning": "true"}
        )
        response = client.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.4, "num_predict": 80},
        )
        summary = response["message"]["content"].strip()
        # Strip any accidental preamble the model adds
        for prefix in ("Sure!", "Of course!", "Here's", "Certainly!", "PANDA:"):
            if summary.startswith(prefix):
                summary = summary[len(prefix):].strip(" ,:")
        return summary if summary else None

    except Exception as e:
        print(f"  [VisionTools] LLM summarise failed (using fallback): {e}")
        return None


def _fallback_summary(state: dict) -> str:
    """
    Clean plain-English fallback used when the LLM is unavailable.
    Much cleaner than the old raw-data concatenation.
    """
    active_window = state.get("active_window", "Unknown")
    response = f"The active window on your screen is '{active_window}'."

    ocr_items = sorted(
        state.get("visible_text", []),
        key=lambda x: x.get("confidence", 0), reverse=True
    )
    top_texts = [t["text"].strip() for t in ocr_items[:3] if t.get("text", "").strip()]
    if top_texts:
        response += f" I can see: {', '.join(top_texts)}."

    clean_controls = _filter_controls(state.get("ui_controls", []))[:3]
    if clean_controls:
        response += f" Controls visible: {', '.join(clean_controls)}."

    return response


# ─── handle_look ─────────────────────────────────────────────────────────────

def handle_look(session_id: str) -> str:
    """
    Captures the screen, runs a full 3-layer analysis, then asks the LLM
    to summarise the data into one natural sentence.
    Saves the observation to memory.
    """
    # 1. Get parent observation ID
    parent_id = None
    try:
        recent = memory_manager.get_recent_observations(session_id, limit=1)
        if recent:
            parent_id = recent[0]["id"]
    except Exception as e:
        print(f"  [VisionTools] Warning loading parent observation: {e}")

    # 2. Build screen state (all 3 layers)
    state = build_screen_state(session_id, parent_observation_id=parent_id)

    # 3. Save a debug screenshot
    try:
        screenshot_path = save_debug_screenshot("look")
        print(f"  [VisionTools] Saved debug screenshot to: {screenshot_path}")
    except Exception as e:
        print(f"  [VisionTools] Error saving screenshot: {e}")

    # 4. Save to DB
    try:
        raw_ocr_json = json.dumps(state["visible_text"])
        memory_manager.add_screen_observation(
            session_id=session_id,
            observation_text=state["summary"],
            raw_ocr_text=raw_ocr_json,
            active_window=state["active_window"],
            parent_observation_id=parent_id
        )
    except Exception as e:
        print(f"  [VisionTools] Error saving screen observation: {e}")

    # 5. LLM summary → fallback if LLM unavailable
    summary = _summarise_screen_with_llm(state)
    return summary if summary else _fallback_summary(state)


# ─── handle_look_text ─────────────────────────────────────────────────────────

def _summarise_text_with_llm(text_lines: list[str]) -> str | None:
    """Uses Ollama to summarize the raw screen text into a natural conversational paragraph."""
    try:
        import ollama
        OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
        MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")

        prompt = (
            "You are PANDA. Summarize the screen text into a natural conversational paragraph.\n"
            "Do NOT use lists or bullet points.\n\n"
            "Screen Text:\n" + "\n".join(text_lines[:30]) + "\n\n"
            "Output format: Reply with ONLY the summary paragraph. No preamble."
        )

        client = ollama.Client(
            host=OLLAMA_URL,
            timeout=30.0,
            headers={"ngrok-skip-browser-warning": "true"}
        )
        response = client.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.4, "num_predict": 120},
        )
        summary = response["message"]["content"].strip()
        for prefix in ("Sure!", "Of course!", "Here's", "Certainly!", "PANDA:"):
            if summary.startswith(prefix):
                summary = summary[len(prefix):].strip(" ,:")
        return summary if summary else None
    except Exception as e:
        print(f"  [VisionTools] LLM text summarise failed: {e}")
        return None


def _fallback_text_summary(text_lines: list[str]) -> str:
    """Friendly fallback when LLM is offline."""
    clean_lines = [line.strip() for line in text_lines if line.strip()]
    if not clean_lines:
        return "I scanned your screen but couldn't detect any text."
    
    sample = clean_lines[:5]
    return f"I read the screen and found some text including: {', '.join(sample)}."


def handle_look_text(session_id: str) -> str:
    """
    Captures screen and returns a summary of all detected text (Layer 2 only).
    """
    try:
        texts = read_screen()
        if not texts:
            return "I read your screen but couldn't detect any text."

        text_lines = [item["text"] for item in texts if item.get("text", "").strip()]
        
        summary = _summarise_text_with_llm(text_lines)
        return summary if summary else _fallback_text_summary(text_lines)
    except Exception as e:
        return f"I encountered an error trying to read the text on screen: {e}"


# ─── handle_find ─────────────────────────────────────────────────────────────

def handle_find(query: str, session_id: str) -> str:
    """
    Finds a named UI element using the 3-layer strategy:
      Layer 1 → Windows UI Automation (accessibility tree)
      Layer 2 → PaddleOCR text match
      Layer 3 → Not used for find (OpenCV is change-detect only)

    No hardcoded templates. No PNG files needed.
    """
    if not query or not query.strip():
        known = list_known_elements()
        sample = known[:6] if known else []
        hint = f" Currently visible elements include: {', '.join(sample)}." if sample else ""
        return f"What should I look for?{hint}"

    query = query.strip()
    result = find_element_dynamic(query)

    if result:
        source_label = {
            "ui_automation": "Windows accessibility tree",
            "ocr":           "screen text (OCR)",
        }.get(result.get("source", ""), result.get("source", "unknown"))

        x1, y1, x2, y2 = result["bbox"]
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        ctrl_type = result.get("control_type", "element")

        response = (
            f"Found '{result['name']}' ({ctrl_type}) via {source_label} "
            f"at X: {center_x}, Y: {center_y}."
        )

        if result.get("confidence") is not None:
            response += f" OCR confidence: {result['confidence']:.0%}."

        return response
    else:
        # Helpful: suggest what IS visible (filtered, no noise)
        known = _filter_controls(list_known_elements())
        if known:
            sample = known[:5]
            return (
                f"I searched for '{query}' using UI Automation and OCR "
                f"but couldn't find it. Visible elements include: {', '.join(sample)}."
            )
        return (
            f"I searched for '{query}' using UI Automation and OCR "
            f"but couldn't find a match on your screen."
        )


# ─── handle_describe_screen ───────────────────────────────────────────────────

def handle_describe_screen(session_id: str) -> str:
    """
    Describes the screen in one natural sentence (LLM-summarised).
    Stores observation to DB.
    """
    parent_id = None
    try:
        recent = memory_manager.get_recent_observations(session_id, limit=1)
        if recent:
            parent_id = recent[0]["id"]
    except Exception as e:
        print(f"  [VisionTools] Warning loading parent observation: {e}")

    state = build_screen_state(session_id, parent_observation_id=parent_id)

    # Save to DB
    try:
        raw_ocr_json = json.dumps(state["visible_text"])
        memory_manager.add_screen_observation(
            session_id=session_id,
            observation_text=state["summary"],
            raw_ocr_text=raw_ocr_json,
            active_window=state["active_window"],
            parent_observation_id=parent_id
        )
    except Exception as e:
        print(f"  [VisionTools] Error saving screen observation in describe: {e}")

    # LLM summary → fallback if LLM unavailable
    summary = _summarise_screen_with_llm(state)
    return summary if summary else _fallback_summary(state)
