"""
PANDA — Browser Controller (Layer 6)
======================================
Selenium-based browser automation for web tasks.
Uses a singleton Chrome WebDriver per PANDA session.

Why Selenium over PyAutoGUI for browser tasks:
  - No pixel coordinate hunting
  - Resolution/zoom independent
  - CSS selector, ID, text, XPath targeting
  - Native page-load waits
  - Reliable form filling, file uploads, dropdown clicks
"""

import threading

_driver = None
_driver_lock = threading.Lock()
_SELENIUM_AVAILABLE = False

try:
    # pyrefly: ignore [missing-import]
    from selenium import webdriver
    # pyrefly: ignore [missing-import]
    from selenium.webdriver.chrome.service import Service as ChromeService
    # pyrefly: ignore [missing-import]
    from selenium.webdriver.common.by import By
    # pyrefly: ignore [missing-import]
    from selenium.webdriver.support.ui import WebDriverWait
    # pyrefly: ignore [missing-import]
    from selenium.webdriver.support import expected_conditions as EC
    # pyrefly: ignore [missing-import]
    from selenium.common.exceptions import (
        NoSuchElementException, TimeoutException, WebDriverException
    )
    _SELENIUM_AVAILABLE = True
except ImportError:
    print("  \033[33m[BrowserController] selenium not installed. "
          "Run: pip install selenium webdriver-manager\033[0m")


def _check_stop():
    """Check the global STOP_EVENT from action_executor."""
    from action.action_executor import STOP_EVENT
    if STOP_EVENT.is_set():
        raise RuntimeError("[BrowserController] Action halted by STOP_EVENT.")


def _check_available():
    if not _SELENIUM_AVAILABLE:
        raise RuntimeError("[BrowserController] selenium is not installed. "
                           "Run: pip install selenium webdriver-manager")


def _get_driver(headless: bool = False):
    """Lazy-init Chrome WebDriver. Reuses across calls (singleton)."""
    global _driver
    _check_available()

    if _driver is not None:
        try:
            # Quick check if driver process is still alive
            if hasattr(_driver, "service") and _driver.service and hasattr(_driver.service, "process") and _driver.service.process:
                if _driver.service.process.poll() is not None:
                    raise RuntimeError("Chrome process is dead")
            _driver.title
            return _driver
        except Exception:
            _driver = None

    with _driver_lock:
        if _driver is None:
            try:
                # pyrefly: ignore [missing-import]
                from webdriver_manager.chrome import ChromeDriverManager

                options = webdriver.ChromeOptions()
                options.add_argument("--start-maximized")
                options.add_argument("--disable-notifications")
                options.add_experimental_option("excludeSwitches", ["enable-logging"])

                if headless:
                    options.add_argument("--headless=new")

                service = ChromeService(ChromeDriverManager().install())
                _driver = webdriver.Chrome(service=service, options=options)
                print("  \033[36m[BrowserController] Chrome WebDriver initialized.\033[0m")
            except Exception as e:
                print(f"  \033[31m[BrowserController] Failed to init Chrome: {e}\033[0m")
                raise RuntimeError(f"Could not start Chrome: {e}")
    return _driver


def open_url(url: str) -> dict:
    """Navigate to any URL."""
    _check_stop()
    try:
        # Auto-add https:// if missing
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        driver = _get_driver()
        driver.get(url)

        # Wait for page to load (up to 10s)
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        return {
            "success": True,
            "title": driver.title,
            "current_url": driver.current_url,
        }
    except RuntimeError:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


def search(query: str, engine: str = "google") -> dict:
    """
    Search the web. Supported engines: google, youtube, bing.
    """
    _check_stop()
    search_urls = {
        "google": f"https://www.google.com/search?q={query.replace(' ', '+')}",
        "youtube": f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
        "bing": f"https://www.bing.com/search?q={query.replace(' ', '+')}",
    }

    engine_lower = engine.lower().strip()
    if engine_lower not in search_urls:
        return {"success": False, "error": f"Unsupported search engine: '{engine}'. Use: google, youtube, bing."}

    return open_url(search_urls[engine_lower])


def click_element_by_text(text: str, timeout: float = 5.0) -> dict:
    """Find and click an element containing the given text."""
    _check_stop()
    try:
        driver = _get_driver()
        xpath = f"//*[contains(text(), '{text}')]"

        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        _check_stop()
        element.click()

        return {
            "success": True,
            "matched_text": element.text[:100],
            "matched_element_tag": element.tag_name,
        }
    except TimeoutException:
        return {"success": False, "error": f"Element with text '{text}' not found or not clickable."}
    except RuntimeError:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


def click_element_by_selector(selector: str, timeout: float = 5.0) -> dict:
    """Click an element by CSS selector."""
    _check_stop()
    try:
        driver = _get_driver()

        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
        )
        _check_stop()
        element.click()

        return {
            "success": True,
            "element_tag": element.tag_name,
        }
    except TimeoutException:
        return {"success": False, "error": f"Element '{selector}' not found or not clickable."}
    except RuntimeError:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


def fill_form_field(selector: str, text: str, clear_first: bool = True) -> dict:
    """Find an input/textarea by CSS selector and type text into it."""
    _check_stop()
    try:
        driver = _get_driver()

        element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

        _check_stop()
        if clear_first:
            element.clear()

        element.send_keys(text)

        return {
            "success": True,
            "field_type": element.get_attribute("type") or element.tag_name,
        }
    except TimeoutException:
        return {"success": False, "error": f"Form field '{selector}' not found."}
    except RuntimeError:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_page_text(max_chars: int = 3000) -> str:
    """Returns visible text of the current page, capped to avoid token overflow."""
    try:
        driver = _get_driver()
        body = driver.find_element(By.TAG_NAME, "body")
        text = body.text or ""
        return text[:max_chars]
    except Exception as e:
        return f"[Error reading page text: {e}]"


def scroll_page(direction: str, amount: int = 3) -> dict:
    """Scroll the page. direction: 'up' or 'down'."""
    _check_stop()
    try:
        driver = _get_driver()
        pixels = 300 * amount

        if direction.lower() == "down":
            driver.execute_script(f"window.scrollBy(0, {pixels})")
        elif direction.lower() == "up":
            driver.execute_script(f"window.scrollBy(0, -{pixels})")
        else:
            return {"success": False, "error": f"Unsupported direction: '{direction}'"}

        return {"success": True, "direction": direction, "pixels": pixels}
    except RuntimeError:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_current_url() -> str:
    """Returns the current browser URL."""
    try:
        driver = _get_driver()
        return driver.current_url
    except Exception:
        return ""


def get_page_title() -> str:
    """Returns the current page title."""
    try:
        driver = _get_driver()
        return driver.title
    except Exception:
        return ""


def close_browser() -> None:
    """Quit the WebDriver and release resources."""
    global _driver
    if _driver is not None:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None
        print("  \033[36m[BrowserController] Browser closed.\033[0m")
