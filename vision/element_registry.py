"""
PANDA Vision — Element Registry (Dynamic Discovery)
=====================================================
Implements the 3-layer element-finding strategy:

  Layer 1 (Primary)  — Windows UI Automation  → finds by accessibility name
  Layer 2 (Fallback) — PaddleOCR text match   → finds by reading visible text
  Layer 3            — OpenCV                  → NOT used for find (change detect only)

No hardcoded templates. No PNG screenshots required.
Elements are discovered dynamically at runtime.

Why we removed the old design:
  - The old KNOWN_ELEMENTS dict mapped names to .png paths
  - All 4 template images were missing — find always failed
  - Even if images existed, they'd break on DPI/theme changes
  - UI Automation is more reliable, faster, and requires zero setup

Built by Aryan — PANDA Vision Sprint 7+
"""

import os
from . import ui_automation_engine
from . import ocr_engine


# ─── 3-Layer Find ─────────────────────────────────────────────────────────────

def find_element_dynamic(query: str) -> dict | None:
    """
    Finds a UI element by name using a 3-layer fallback strategy.

    Args:
        query: Human-readable element name, e.g. "Send", "search box", "Submit button"

    Returns a dict on success:
      {
        "name":         str,           # matched element name
        "control_type": str,           # e.g. "ButtonControl" / "text_ocr"
        "bbox":         [x1,y1,x2,y2], # screen coordinates
        "source":       str,           # "ui_automation" | "ocr"
        "confidence":   float | None   # set by OCR layer, None for UI auto
      }
    Returns None if no layer found anything.
    """

    # ── Layer 1: Windows UI Automation ────────────────────────────────────────
    result = _layer1_ui_automation(query)
    if result:
        print(f"  \033[36m[Vision] Found '{query}' via Layer 1 (UI Automation)\033[0m", flush=True)
        return result

    # ── Layer 2: PaddleOCR Text Match ─────────────────────────────────────────
    result = _layer2_ocr_match(query)
    if result:
        print(f"  \033[36m[Vision] Found '{query}' via Layer 2 (OCR match)\033[0m", flush=True)
        return result

    print(f"  \033[33m[Vision] '{query}' not found in any layer.\033[0m", flush=True)
    return None


def _layer1_ui_automation(query: str) -> dict | None:
    """
    Layer 1: Query the Windows accessibility tree for an element
    whose accessible name contains `query`.
    """
    if not ui_automation_engine.is_available():
        return None
    return ui_automation_engine.find_element(query)


def _layer2_ocr_match(query: str) -> dict | None:
    """
    Layer 2: Capture screen, run PaddleOCR, fuzzy-match `query`
    against all detected text regions.

    Matching strategy:
      1. Exact substring match (case-insensitive)  → highest priority
      2. All query words present in text           → medium priority
      Returns the highest-confidence match above threshold.
    """
    try:
        texts = ocr_engine.read_screen()
    except Exception as e:
        print(f"  [Vision/OCR] Error reading screen: {e}")
        return None

    if not texts:
        return None

    query_lower = query.lower().strip()
    query_words = query_lower.split()

    best_match = None
    best_score = 0.0

    for item in texts:
        text = item.get("text", "").strip()
        confidence = item.get("confidence", 0.0)
        bbox = item.get("bbox", [])

        if not text or confidence < 0.5 or not bbox:
            continue

        text_lower = text.lower()

        # Score: exact substring match wins
        if query_lower in text_lower:
            score = confidence + 1.0   # boost for exact match
        elif all(w in text_lower for w in query_words):
            score = confidence + 0.5   # boost for all-words match
        elif any(w in text_lower for w in query_words if len(w) > 2):
            score = confidence * 0.8   # partial match, lower weight
        else:
            continue

        if score > best_score:
            best_score = score
            best_match = {
                "name":         text,
                "control_type": "text_ocr",
                "bbox":         [int(b) for b in bbox],  # [x1, y1, x2, y2]
                "source":       "ocr",
                "confidence":   round(float(confidence), 3),
            }

    return best_match


# ─── Utility ──────────────────────────────────────────────────────────────────

def list_known_elements() -> list[str]:
    """
    Returns a list of all named UI controls currently visible on screen.
    Uses Layer 1 (UI Automation). Falls back to OCR text list.

    This replaces the old static KNOWN_ELEMENTS dict — now dynamic.
    """
    # Try UI Automation first
    if ui_automation_engine.is_available():
        controls = ui_automation_engine.get_all_controls()
        if controls:
            return sorted({c["name"] for c in controls if c.get("name")})

    # Fallback: OCR text labels
    try:
        texts = ocr_engine.read_screen()
        return sorted({t["text"].strip() for t in texts if t.get("text", "").strip()})
    except Exception:
        return []

# ─── Backward Compatibility Registry ──────────────────────────────────────────

_registry = {
    "chrome": os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "chrome_icon.png")
}

def register_element(name: str, template_path: str):
    key = name.lower().replace("-", "_")
    _registry[key] = template_path

def resolve_element(name: str) -> str | None:
    key = name.lower().replace("-", "_")
    return _registry.get(key)




