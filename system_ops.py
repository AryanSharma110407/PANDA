"""
✨ PANDA — System Operations Module
====================================
This module handles everything related to your computer:
- Opening applications (Notepad, Calculator, VS Code, etc.)
- Opening websites (YouTube, GitHub, Gmail, etc.)
- Searching Google and YouTube
- Getting system info (CPU, RAM, Disk)
- Taking screenshots
- Opening the project folder

What you're learning here:
- os module → interacting with Windows
- subprocess → launching other programs  
- webbrowser → opening URLs
- platform + psutil → reading system info
- Pillow (PIL) → capturing screenshots
- Dictionaries → mapping names to commands/URLs
"""

import os
import subprocess
import webbrowser
import platform
import datetime

# Try importing optional packages — PANDA still works without them
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    # pyrefly: ignore [missing-import]
    from PIL import ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ─── APP DICTIONARY ───────────────────────────────────────────────────────────
# Maps friendly names to Windows commands
# You can add your own apps here!

APPS = {
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "paint": "mspaint",
    "explorer": "explorer",
    "file explorer": "explorer",
    "cmd": "cmd",
    "command prompt": "cmd",
    "terminal": "cmd",
    "powershell": "powershell",
    "task manager": "taskmgr",
    "control panel": "control",
    "settings": "start ms-settings:",
    "snipping tool": "snippingtool",
    "wordpad": "write",
    "vscode": "code",
    "vs code": "code",
    "chrome": "start chrome",
    "edge": "start msedge",
    "brave": "start brave",
}


# ─── WEBSITE DICTIONARY ──────────────────────────────────────────────────────
# Maps friendly names to URLs

WEBSITES = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chat.openai.com",
    "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "reddit": "https://www.reddit.com",
    "stackoverflow": "https://stackoverflow.com",
    "linkedin": "https://www.linkedin.com",
    "spotify": "https://open.spotify.com",
    "netflix": "https://www.netflix.com",
    "drive": "https://drive.google.com",
    "classroom": "https://classroom.google.com",
    "maps": "https://maps.google.com",
    "translate": "https://translate.google.com",
}


# ─── FUNCTIONS ────────────────────────────────────────────────────────────────

def open_app(app_name):
    """
    Opens a desktop application by name.
    Uses the APPS dictionary to find the right command.
    
    What you're learning:
    - Dictionary lookups with .get()
    - subprocess for running system commands
    - Error handling for missing apps
    """
    app_name = app_name.lower().strip()
    
    if app_name in APPS:
        try:
            command = APPS[app_name]
            # 'start' commands need shell=True on Windows
            if command.startswith("start"):
                os.system(command)
            else:
                subprocess.Popen(command, shell=True)
            return f"🚀 Opening {app_name.title()}..."
        except Exception as e:
            return f"❌ Couldn't open {app_name}: {e}"
    else:
        # Try to open it directly — maybe it's in PATH
        try:
            subprocess.Popen(app_name, shell=True)
            return f"🚀 Trying to open {app_name}..."
        except Exception:
            available = ", ".join(sorted(APPS.keys()))
            return f"❌ I don't know that app. Available apps: {available}"


def open_website(site_name):
    """
    Opens a website by its friendly name.
    
    What you're learning:
    - webbrowser module — Python's built-in URL opener
    - Dictionary lookups
    """
    site_name = site_name.lower().strip()
    
    if site_name in WEBSITES:
        url = WEBSITES[site_name]
        webbrowser.open(url)
        return f"🌐 Opening {site_name.title()}..."
    elif site_name.startswith("http://") or site_name.startswith("https://"):
        webbrowser.open(site_name)
        return f"🌐 Opening {site_name}..."
    elif "." in site_name:
        # Looks like a URL without https://
        webbrowser.open(f"https://{site_name}")
        return f"🌐 Opening {site_name}..."
    else:
        available = ", ".join(sorted(WEBSITES.keys()))
        return f"❌ I don't know that site. Available sites: {available}"


def search_google(query):
    """
    Searches Google for anything.
    
    What you're learning:
    - URL encoding (replacing spaces with +)
    - Building URLs dynamically
    """
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    return f"🔍 Searching Google for: {query}"


def search_youtube(query):
    """
    Searches YouTube for anything.
    """
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    webbrowser.open(url)
    return f"🎬 Searching YouTube for: {query}"


def get_system_info():
    """
    Gets a complete system dashboard — CPU, RAM, Disk usage.
    
    What you're learning:
    - platform module — OS information
    - psutil — real-time system monitoring (used in DevOps!)
    - String formatting — building readable output

    PERFORMANCE FIX: cpu_percent(interval=None) returns instantly using the
    cached value from the last call. interval=1 used to block for a full second
    every time this function ran, making PANDA feel frozen.
    """
    info = []
    info.append("╔══════════════════════════════════════╗")
    info.append("║        🖥️  SYSTEM DASHBOARD          ║")
    info.append("╚══════════════════════════════════════╝")
    info.append("")
    
    # OS Info (always available)
    info.append(f"  💻 OS: {platform.system()} {platform.release()}")
    info.append(f"  🏗️  Architecture: {platform.machine()}")
    info.append(f"  🖥️  Computer: {platform.node()}")
    info.append(f"  🐍 Python: {platform.python_version()}")
    
    # Detailed info (requires psutil)
    if PSUTIL_AVAILABLE:
        info.append("")
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        info.append(f"  ⚡ CPU Usage: {cpu_percent}% ({cpu_count} cores)")
        
        # RAM
        ram = psutil.virtual_memory()
        ram_total = round(ram.total / (1024**3), 1)
        ram_used = round(ram.used / (1024**3), 1)
        info.append(f"  🧠 RAM: {ram_used}GB / {ram_total}GB ({ram.percent}%)")
        
        # Disk
        disk = psutil.disk_usage('/')
        disk_total = round(disk.total / (1024**3), 1)
        disk_used = round(disk.used / (1024**3), 1)
        info.append(f"  💾 Disk: {disk_used}GB / {disk_total}GB ({disk.percent}%)")
        
        # Battery
        battery = psutil.sensors_battery()
        if battery:
            plug = "🔌 Plugged in" if battery.power_plugged else "🔋 On battery"
            info.append(f"  🔋 Battery: {battery.percent}% ({plug})")
    else:
        info.append("")
        info.append("  ⚠️  Install psutil for detailed stats: pip install psutil")
    
    return "\n".join(info)


def take_screenshot():
    """
    Takes a screenshot and saves it to the screenshots folder.
    
    What you're learning:
    - Pillow (PIL) library — image processing
    - os.makedirs — creating directories
    - datetime formatting — creating unique filenames
    """
    if not PIL_AVAILABLE:
        return "❌ Screenshot requires Pillow. Run: pip install Pillow"
    
    # Create screenshots folder if it doesn't exist
    screenshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    
    # Create a unique filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(screenshot_dir, f"screenshot_{timestamp}.png")
    
    try:
        screenshot = ImageGrab.grab()
        screenshot.save(filepath)
        return f"📸 Screenshot saved: {filepath}"
    except Exception as e:
        return f"❌ Screenshot failed: {e}"


def open_project_folder():
    """Opens the PANDA project folder in File Explorer."""
    folder = os.path.dirname(os.path.abspath(__file__))
    os.startfile(folder)
    return f"📂 Opening folder: {folder}"


def open_weather():
    """Opens weather forecast for your city."""
    # Change this to your city!
    city = "your+city"
    webbrowser.open(f"https://www.google.com/search?q=weather+{city}")
    return "🌤️ Opening weather forecast..."


def open_news():
    """Opens tech news."""
    webbrowser.open("https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pKVGlnQVAB")
    return "📰 Opening tech news..."


def list_apps():
    """Lists all available apps that PANDA can open."""
    apps = sorted(set(APPS.keys()))
    result = "📱 Available apps:\n"
    for app in apps:
        result += f"   • {app}\n"
    return result.strip()


def list_sites():
    """Lists all available websites that PANDA can open."""
    sites = sorted(set(WEBSITES.keys()))
    result = "🌐 Available websites:\n"
    for site in sites:
        result += f"   • {site}\n"
    return result.strip()
