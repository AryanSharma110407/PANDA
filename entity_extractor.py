"""
 PANDA — Entity Extractor 
===================================================
Replaces the earlier dateparser stub with a two-stage pipeline:

  Stage 1 — spaCy NER  (structural understanding)
      en_core_web_sm identifies named entities in the sentence.
      We specifically look for DATE and TIME labels, which spaCy is
      trained to find in natural phrases like:
          "tomorrow at 6", "next Friday", "in 20 minutes", "at noon"

  Stage 2 — dateparser  (semantic resolution)
      Takes the raw entity *string* spaCy found and converts it to an
      actual datetime object, anchored to "prefer future dates".
      dateparser handles ambiguous phrases like "Friday" → next Friday,
      "6" → 6 PM if it's currently afternoon, etc.

  Stage 3 — Full-text fallback
      If spaCy found no DATE/TIME entity (e.g. the phrase was too short
      or informal), dateparser runs on the entire input as a last resort.
      This preserves Mark I behaviour for short inputs like "in 5 mins".


What you're learning here
--------------------------
- spaCy — the industry-standard Python NLP library
- Named Entity Recognition (NER) — identifying "things" in text
  (people, places, organisations, dates, times, money, …)
- Pipeline composition — chaining two models for better accuracy
- Graceful degradation — if spaCy fails to load, fall back to Mark I
- Lazy model loading — load the heavy model once, reuse on every call

Installation (run once)
-----------------------
    pip install spacy
    python -m spacy download en_core_web_sm
"""

from __future__ import annotations
import dateparser
import re

_nlp = None
_spacy_available = True


def _get_nlp():
    """
    Returns the cached spaCy pipeline, loading it on first call.

    What you're learning:
    - Lazy initialisation — defer expensive work until it's actually needed.
      Common in production systems where startup time matters.
    - Module-level singletons — _nlp lives at module scope so every call
      to extract_entities() shares the same loaded model.
    """
    global _nlp, _spacy_available

    if _nlp is not None:
        return _nlp

    if not _spacy_available:
        return None

    try:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
        return _nlp

    except ImportError:
        print(
            "  \033[33m[EntityExtractor] spaCy not installed.\n"
            "  Run: pip install spacy && python -m spacy download en_core_web_sm\033[0m"
        )
        _spacy_available = False
        return None

    except OSError:
        print(
            "  \033[33m[EntityExtractor] en_core_web_sm model not found.\n"
            "  Run: python -m spacy download en_core_web_sm\033[0m"
        )
        _spacy_available = False
        return None


# ─── Dateparser settings ──────────────────────────────────────────────────────

_DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "future",   # "Friday" → next Friday, not last
    "RETURN_AS_TIMEZONE_AWARE": False,
}


def clean_task_text(text: str, time_ent_text: str | None = None) -> str:
    """
    Cleans task text by removing time expressions and reminder verb prefixes.
    """
    cleaned = text.strip()
    
    # 1. Remove the time entity text if present
    if time_ent_text:
        pattern = re.compile(re.escape(time_ent_text), re.IGNORECASE)
        cleaned = pattern.sub("", cleaned).strip()
    else:
        # Fallback: remove some common simple time phrases if they exist and no time_ent was given
        common_time_patterns = [
            r"\bin\s+\d+\s*(?:mins?|minutes?|hours?|days?)\b",
            r"\bat\s+\d+(?::\d+)?\s*(?:am|pm)?\b",
            r"\btomorrow\b",
            r"\btoday\b",
            r"\btonight\b",
            r"\bnext\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
        ]
        for pat in common_time_patterns:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
    
    # 2. Clean up common reminder trigger prefixes
    prefixes = [
        r"^remind\s+me\s+to\s+",
        r"^remind\s+me\s+for\s+",
        r"^remind\s+me\s+",
        r"^set\s+a\s+reminder\s+to\s+",
        r"^set\s+a\s+reminder\s+for\s+",
        r"^set\s+reminder\s+to\s+",
        r"^set\s+reminder\s+for\s+",
        r"^reminder\s+to\s+",
        r"^reminder\s+for\s+",
        r"^remind\s+to\s+",
        r"^remind\s+",
    ]
    
    for prefix in prefixes:
        cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE).strip()
        
    # 3. Clean up leading "to " if any remains
    cleaned = re.sub(r"^to\s+", "", cleaned, flags=re.IGNORECASE).strip()
    
    # Clean up double spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    return cleaned


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def extract_entities(text: str, intent: str | None = None) -> dict:
    """
    Extracts structured entities from a raw user utterance.

    Parameters
    ----------
    text    Raw user input, e.g. "remind me tomorrow at 6 to call mum"
    intent  Current intent from the router, e.g. "reminder".
            Used to decide which task-extraction heuristic to apply.

    Returns
    -------
    dict with any of:
        "time"  → datetime object  (when)
        "task"  → str              (what to do)

    Examples
    --------
    >>> extract_entities("remind me at 9 pm to drink water", intent="reminder")
    {"time": datetime(2025, ..., 21, 0), "task": "drink water"}

    >>> extract_entities("what time is it")
    {}
    """
    data: dict = {}
    time_text = None

    # ── Stage 1 + 2: spaCy NER → dateparser ───────────────────────────────
    nlp = _get_nlp()

    if nlp is not None:
        # Three lines of real NER ↓
        doc      = nlp(text)
        time_ent = next((e for e in doc.ents if e.label_ in ("DATE", "TIME")), None)

        if time_ent:
            dt = dateparser.parse(time_ent.text, settings=_DATEPARSER_SETTINGS)
            if dt:
                data["time"] = dt
                time_text = time_ent.text

    # ── Stage 3: full-text dateparser fallback ────────────────────────────
    # Runs when spaCy found no entity — catches short phrases spaCy misses,
    # e.g. "in 5 minutes", "now", or inputs when the model isn't installed.
    if "time" not in data:
        dt = dateparser.parse(text, settings=_DATEPARSER_SETTINGS)
        if dt:
            data["time"] = dt

    # ── Task extraction (intent-specific heuristic) ────────────────────────
    if intent == "reminder":
        task = clean_task_text(text, time_text)
        if task:
            data["task"] = task

    return data