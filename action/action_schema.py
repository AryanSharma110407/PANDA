"""
PANDA — Action Schema (Layer 0)
================================
Registry of every action PANDA is allowed to take.
Sprint 9's dynamic action planner can ONLY generate actions that exist here.
This is the safety contract between the LLM and the execution engine.
"""


VALID_ACTIONS = {
    "click",
    "right_click",
    "type",
    "press",
    "scroll",
    "drag",
    "browser_open",
    "browser_search",
    "browser_fill",
    "browser_click",
    "browser_scroll",
    "system_search",
    "select_and_copy",
    "undo",
    "complete",
    "fail",
}

ACTION_SCHEMAS = {
    "click":          {"required": ["target"],            "optional": [],         "description": "Click on a visible UI element by text or icon"},
    "right_click":    {"required": ["target"],            "optional": [],         "description": "Right click on a visible UI element by text or icon"},
    "type":           {"required": ["text"],              "optional": ["clear_first"], "description": "Type text into the currently focused field"},
    "press":          {"required": ["key"],               "optional": [],         "description": "Press a keyboard key (e.g. 'enter', 'tab', 'escape')"},
    "scroll":         {"required": ["direction"],         "optional": ["amount"], "description": "Scroll the screen 'up' or 'down'"},
    "drag":           {"required": ["source", "target"],  "optional": ["duration"], "description": "Drag from source element to target element"},
    "browser_open":   {"required": ["url"],               "optional": [],         "description": "Open a specific URL in the browser"},
    "browser_search": {"required": ["query"],             "optional": ["engine"], "description": "Search the web directly (engine can be 'google', 'youtube', 'bing') WITHOUT needing to open the browser or click a search bar first"},
    "browser_fill":   {"required": ["selector", "text"],  "optional": [],         "description": "Fill a web form field using a CSS selector"},
    "browser_click":  {"required": ["selector"],          "optional": [],         "description": "Click a web element using a CSS selector"},
    "browser_scroll": {"required": ["direction"],         "optional": ["amount"], "description": "Scroll the browser window 'up' or 'down'"},
    "system_search":  {"required": ["query"],             "optional": [],         "description": "Search the OS for an app or file by pressing the Windows key, typing the query, and hitting Enter (e.g. use this to open Notepad)"},
    "select_and_copy": {"required": ["target"],            "optional": [],         "description": "Click on a text field, label, or element, select all text (Ctrl+A), and copy it to clipboard (Ctrl+C). Returns the copied text."},
    "undo":           {"required": [],                    "optional": [],         "description": "Undo the last click or type action to recover from mistakes"},
    "complete":       {"required": [],                    "optional": [],         "description": "Signal that the current milestone or task is fully achieved"},
    "fail":           {"required": ["reason"],            "optional": [],         "description": "Signal that the task is blocked and cannot continue"},
}


def is_valid_action(action_type: str) -> bool:
    """Returns True if action_type is in the valid action set."""
    return action_type in VALID_ACTIONS


def validate_action(action_type: str, params: dict) -> tuple[bool, str]:
    """
    Validates an action against its schema.
    Returns (is_valid, error_message). Empty error string means valid.
    """
    if action_type not in ACTION_SCHEMAS:
        return False, f"Unknown action: '{action_type}'"
    schema = ACTION_SCHEMAS[action_type]
    for req in schema["required"]:
        if req not in params:
            return False, f"Missing required param '{req}' for action '{action_type}'"
    return True, ""


def get_action_info(action_type: str) -> dict | None:
    """Returns the schema info for a given action, or None if unknown."""
    if action_type not in ACTION_SCHEMAS:
        return None
    return {
        "action": action_type,
        "required": ACTION_SCHEMAS[action_type]["required"],
        "optional": ACTION_SCHEMAS[action_type]["optional"],
    }


def list_all_actions() -> list[str]:
    """Returns a sorted list of all valid actions."""
    return sorted(VALID_ACTIONS)
