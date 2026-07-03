"""
PANDA Vision — Semantic UI Builder
====================================
Fuses Windows UI Automation (Layer 1) and OCR (Layer 2) outputs
into a clean, structured, and semantically-typed representation
of the screen for the LLM Actor.
"""

# Map native Windows IUIAutomation Control Types to human-readable types
CONTROL_TYPE_MAP = {
    "ButtonControl": "Button",
    "HyperlinkControl": "Hyperlink",
    "EditControl": "TextInput",
    "CheckBoxControl": "CheckBox",
    "ComboBoxControl": "Dropdown",
    "ListItemControl": "ListItem",
    "MenuItemControl": "MenuItem",
    "RadioButtonControl": "RadioButton",
    "TabItemControl": "Tab",
    "TextControl": "StaticText",
    "DocumentControl": "TextRegion",
    "PaneControl": "Pane",
    "GroupControl": "Group",
}

def build_semantic_ui(ui_controls: list[dict], ocr_results: list[dict]) -> list[dict]:
    """
    Fuses UI controls from Layer 1 and OCR lines from Layer 2.
    Returns a list of clean, semantic dictionary items representing elements on the screen.
    
    Each item:
      {
        "type": str,       # e.g. "Button", "Hyperlink", "TextInput", "StaticText"
        "label": str,      # Accessible name or visible text
        "bbox": list,      # [left, top, right, bottom]
        "interactive": bool
      }
    """
    semantic_elements = []
    
    # 1. Process UI Automation Controls
    for ctrl in ui_controls:
        name = ctrl.get("name", "").strip()
        if not name:
            continue
            
        raw_type = ctrl.get("control_type", "PaneControl")
        mapped_type = CONTROL_TYPE_MAP.get(raw_type, "Pane")
        
        # Guard: Filter out large container panes/documents to prevent clicking the center of the screen
        bbox = ctrl.get("bbox", [0, 0, 0, 0])
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        
        # Skip if it is a massive structural container (width or height > 1200)
        if mapped_type in ("Pane", "Group", "TextRegion") and (w > 1200 or h > 800):
            continue
            
        semantic_elements.append({
            "type": mapped_type,
            "label": name,
            "bbox": bbox,
            "interactive": ctrl.get("is_interactive", False) or mapped_type in ("Button", "Hyperlink", "TextInput", "CheckBox", "Dropdown")
        })
        
    # 2. De-duplicate OCR vs UI Automation
    # If some OCR texts are not inside the bounding boxes of any UI Automation elements,
    # we include them as StaticText or PotentialClickable elements.
    for ocr in ocr_results:
        text = ocr.get("text", "").strip()
        if not text or len(text) < 2:
            continue
            
        ocr_bbox = ocr.get("bbox", [0, 0, 0, 0])
        ox1, oy1, ox2, oy2 = ocr_bbox
        
        # Check if this OCR block is already covered by a UI Automation control
        is_covered = False
        for elem in semantic_elements:
            ex1, ey1, ex2, ey2 = elem["bbox"]
            # Strict overlap check (if center of OCR text is inside the UI Automation element box)
            ocx = (ox1 + ox2) / 2
            ocy = (oy1 + oy2) / 2
            if ex1 <= ocx <= ex2 and ey1 <= ocy <= ey2:
                is_covered = True
                break
                
        if not is_covered:
            # Add it as a generic text region
            semantic_elements.append({
                "type": "StaticText",
                "label": text,
                "bbox": ocr_bbox,
                "interactive": False
            })
            
    # Clean up duplicate names with identical types
    unique_elements = []
    seen = set()
    for el in semantic_elements:
        key = (el["type"], el["label"].lower())
        if key not in seen:
            seen.add(key)
            unique_elements.append(el)
            
    return unique_elements
