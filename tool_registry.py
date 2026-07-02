"""
🗂️ PANDA — Tool Registry  (Mark IV)
=====================================
A central registry that maps tool names → callable functions.

This is the standard "Plugin / Registry" design pattern used in
professional frameworks (Flask routes, Django apps, LangChain tools, etc.).

Adding a new tool? Two steps:
  1. Build the function in its own module (e.g. perception_tools.py)
  2. Register it here under a unique string key

The agent (PANDA / alya.py) always goes through this registry — it never
imports tool modules directly. This keeps the agent decoupled from the
tool implementations.

What you're learning:
- Registry / Plugin pattern
- Dependency inversion principle (depend on abstractions, not concretions)
- How LangChain, AutoGPT, and other agentic frameworks manage tool dispatch

Mark IV note:
- listen_to_user now uses faster-whisper small model (fully offline)
- ContinuousListener handles the always-on mic mode (see perception_tools.py)
"""

from perception_tools import listen_to_user, list_microphones, select_microphone

# ─── Master Tool Registry ────────────────────────────────────────────────────
# Format:  "tool_name": callable
#
# The callable must return a dict. Required keys:
#   {"status": "success" | "error", ...}
#
# On success, data is passed back to the agent.
# On error,   "message" key explains what went wrong.

TOOLS: dict = {
    # ── Perception ────────────────────────────────────────────────────────
    "listen_to_user":     listen_to_user,
    "list_microphones":   list_microphones,
    "select_microphone":  select_microphone,
    # ── (Future tools go here) ─────────────────────────────────────────────
    # "read_clipboard":  read_clipboard,
    # "capture_screen":  capture_screen,
    # "detect_emotion":  detect_emotion,
}


def get_tool(name: str):
    """
    Returns the callable for the given tool name, or None if not found.

    Usage:
        fn = get_tool("listen_to_user")
        if fn:
            result = fn()
    """
    return TOOLS.get(name)


def list_tools() -> list[str]:
    """Returns a sorted list of all registered tool names."""
    return sorted(TOOLS.keys())


def run_tool(name: str, **kwargs) -> dict:
    """
    Looks up and executes a tool by name.

    Returns the tool's result dict, or an error dict if the tool
    doesn't exist.

    Usage:
        result = run_tool("listen_to_user")
    """
    fn = get_tool(name)
    if fn is None:
        return {
            "status":  "error",
            "message": f"Unknown tool: '{name}'. Available: {list_tools()}",
        }
    return fn(**kwargs)
