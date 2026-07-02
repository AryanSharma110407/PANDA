"""
PANDA — Browser Controller (Default Browser/Brave Integration)
===============================================================
Dynamic browser routing using the user's default browser (Brave).

Instead of managing a separate, clean-slate Selenium WebDriver (which is easily
detected by Google and requires re-login), this module commands the OS
to open URLs directly in the user's active default browser.
"""

import os
import subprocess
import webbrowser

# Compatibility variables
_SELENIUM_AVAILABLE = False
_driver = None

def _check_stop():
    """Check the global STOP_EVENT from action_executor."""
    from action.action_executor import STOP_EVENT
    if STOP_EVENT.is_set():
        raise RuntimeError("[BrowserController] Action halted by STOP_EVENT.")

def _check_available():
    pass

def _open_in_brave_or_default(url: str) -> bool:
    """
    Attempts to open a URL directly in the Brave browser.
    Falls back to Python's native webbrowser (system default) if Brave is not found.
    """
    paths = [
        os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe")
    ]
    
    for path in paths:
        if os.path.exists(path):
            try:
                subprocess.Popen([path, url])
                return True
            except Exception:
                pass
                
    # Fallback to webbrowser (opens system default browser)
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False

def open_url(url: str) -> dict:
    """
    Opens the URL in Brave or the default browser.
    """
    _check_stop()
    try:
        # Auto-add https:// if missing
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        print(f"  [BrowserController] Opening '{url}' in default browser...")
        success = _open_in_brave_or_default(url)
        
        return {
            "success": success,
            "title": "Brave Browser Tab",
            "current_url": url,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def search(query: str, engine: str = "google") -> dict:
    """
    Constructs a search URL and opens it in the browser.
    Supported engines: google, youtube, bing.
    """
    _check_stop()
    search_urls = {
        "google": f"https://www.google.com/search?q={query.replace(' ', '+')}",
        "youtube": f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
        "bing": f"https://www.bing.com/search?q={query.replace(' ', '+')}",
    }

    engine_lower = engine.lower().strip()
    if engine_lower not in search_urls:
        return {"success": False, "error": f"Unsupported search engine: '{engine}'"}

    return open_url(search_urls[engine_lower])


# ── Compatibility Stubs for Deprecated Selenium API ──────────────────────────

def click_element_by_text(text: str, timeout: float = 5.0) -> dict:
    return {"success": False, "error": "Selenium actions are deprecated. Use standard GUI click actions."}

def click_element_by_selector(selector: str, timeout: float = 5.0) -> dict:
    return {"success": False, "error": "Selenium actions are deprecated. Use standard GUI click actions."}

def fill_form_field(selector: str, text: str, clear_first: bool = True) -> dict:
    return {"success": False, "error": "Selenium actions are deprecated. Use standard GUI type actions."}

def get_page_text(max_chars: int = 3000) -> str:
    return "[Page text retrieval is deprecated. Use screen OCR elements.]"

def scroll_page(direction: str, amount: int = 3) -> dict:
    return {"success": False, "error": "Selenium actions are deprecated. Use standard GUI scroll actions."}

def get_current_url() -> str:
    return ""

def get_page_title() -> str:
    return ""

def close_browser() -> None:
    pass
