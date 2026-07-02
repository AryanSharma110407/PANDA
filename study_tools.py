"""
✨ PANDA — Study Tools Module
===============================
This module helps you study better:
- Pomodoro/study timer with countdown
- Desktop notification reminders
- Daily schedule suggestion
- Quick calculator

What you're learning here:
- Threading — running code in parallel (timers in background)
- Desktop notifications — OS-level alerts via plyer
- time.sleep() — pausing execution
- Input validation — checking user input before using it
- daemon vs non-daemon threads — the difference between "fire and forget"
  and "keep alive until the job is done"
- Registry pattern — tracking live threads so nothing gets silently lost
"""

import time
import threading
import datetime
import re

# Try importing plyer for desktop notifications
try:
    # pyrefly: ignore [missing-import]
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False

try:
    import voice
    _VOICE_AVAILABLE = True
except ImportError:
    _VOICE_AVAILABLE = False


# ─── ACTIVE REMINDER TRACKER ──────────────────────────────────────────────────
# Why this matters:
#   daemon=True threads are "fire and forget" — the OS kills them the moment
#   the main program exits or the event loop moves on. That's fine for a timer
#   where you don't mind if it vanishes, but a reminder that silently dies is
#   a broken promise to the user.
#
#   Keeping non-daemon threads in a list does two things:
#     1. Python won't exit until every thread in this list finishes — so the
#        reminder fires even if PANDA is "idle".
#     2. We can inspect the list to show the user what's pending.
#
# What you're learning:
#   - Non-daemon threads keep the process alive — daemon threads don't.
#   - A simple list as a "live job registry" is the same concept used by
#     task queues (Celery, RQ) and async job runners.

_active_reminders: list = []    # [{"thread": Thread, "fires_at": str, "message": str}]
_reminders_lock = threading.Lock()   # guards reads/writes to the list


def _cleanup_finished_reminders():
    """Prunes completed reminder entries so the list stays lean."""
    with _reminders_lock:
        still_running = [r for r in _active_reminders if r["thread"].is_alive()]
        _active_reminders.clear()
        _active_reminders.extend(still_running)


def list_active_reminders() -> str:
    """
    Shows all reminders that haven't fired yet.
    Useful when the user asks 'what reminders do I have?'
    """
    _cleanup_finished_reminders()
    with _reminders_lock:
        pending = list(_active_reminders)   # snapshot so we can release the lock

    if not pending:
        return "🔕 No active reminders right now."

    lines = ["  🔔 Active Reminders:"]
    for r in pending:
        lines.append(f"     • At {r['fires_at']} — \"{r['message']}\"")
    return "\n".join(lines)


# ─── STUDY TIMER ──────────────────────────────────────────────────────────────

def start_timer(minutes):
    """
    Starts a study/pomodoro timer that runs in the background.
    When the timer ends, you get a desktop notification!
    
    What you're learning:
    - Threading — running a function in the background
    - time.sleep() — pausing execution for a set time
    - Desktop notifications — how apps alert you
    """
    try:
        minutes = int(minutes)
    except (ValueError, TypeError):
        return "❌ Please provide minutes! Usage: timer <minutes>"
    
    if minutes <= 0:
        return "❌ Timer must be at least 1 minute!"
    if minutes > 300:
        return "❌ That's over 5 hours! Let's be reasonable 😄"
    
    def _timer_thread(mins):
        """This runs in a separate thread — it won't block PANDA!"""
        time.sleep(mins * 60)
        
        # Send desktop notification when timer ends
        if PLYER_AVAILABLE:
            try:
                notification.notify(
                    title="✨ PANDA Timer",
                    message=f"⏰ Your {mins}-minute timer is up! Great work!",
                    app_name="PANDA",
                    timeout=10
                )
            except Exception:
                pass
        
        print(f"\n\n  ⏰ ══════════════════════════════════════")
        print(f"  ⏰  TIMER DONE! {mins} minutes are up!")
        print(f"  ⏰  Great work! Take a break! 🎉")
        print(f"  ⏰ ══════════════════════════════════════\n")
    
    # Start timer in a background thread (daemon=True means it dies with the main program)
    timer_thread = threading.Thread(target=_timer_thread, args=(minutes,), daemon=True)
    timer_thread.start()
    
    end_time = (datetime.datetime.now() + datetime.timedelta(minutes=minutes)).strftime("%H:%M")
    return f"⏱️ Timer set for {minutes} minute(s)! Ends at {end_time}. Keep working! 💪"


# ─── REMINDERS ────────────────────────────────────────────────────────────────

def set_reminder(minutes, message):
    """
    Sets a reminder that fires after the given number of minutes.

    KEY FIX — daemon=False:
        The old code used daemon=True, which let the OS silently kill the
        reminder thread if the main loop moved on. That's why "nothing happened".

        daemon=False tells Python: "keep the process alive until this thread
        finishes its job." The reminder WILL fire — no matter what PANDA is doing.

    KEY FIX — tracker registration:
        We store each live reminder in _active_reminders so:
          • You can ask "what reminders do I have?"
          • We can prove the thread actually started

    What you're learning:
    - daemon vs non-daemon threads (the root cause of the bug!)
    - Thread registry pattern — same idea as Celery's task tracking
    - threading.Lock for safe concurrent list access
    """
    try:
        minutes = int(minutes)
    except (ValueError, TypeError):
        return "❌ Please provide minutes! Usage: remind <minutes> <message>"

    if minutes <= 0:
        return "❌ Reminder must be at least 1 minute in the future!"

    message = message.strip() or "Hey! You set a reminder!"

    def _reminder_thread(mins, msg):
        time.sleep(mins * 60)

        # 1. Speak aloud
        if _VOICE_AVAILABLE:
            try:
                voice.speak(f"Reminder: {msg}")
            except Exception as e:
                print(f"\n[Voice Error] Failed to speak: {e}")

        # 2. Show the unignorable topmost popup
        try:
            from task_manager import show_unignorable_popup
            show_unignorable_popup("⏰ PANDA Reminder Alert", f"Reminder: {msg}")
        except Exception as e:
            print(f"\n[Popup Error] Failed to show popup: {e}")

        # Always print to console as a guaranteed fallback
        print(f"\n\n  🔔 ══════════════════════════════════════")
        print(f"  🔔  REMINDER: {msg}")
        print(f"  🔔 ══════════════════════════════════════\n")

    fires_at = (
        datetime.datetime.now() + datetime.timedelta(minutes=minutes)
    ).strftime("%H:%M")

    # FIX: daemon=False — thread outlives idle periods and ALWAYS fires
    thread = threading.Thread(
        target=_reminder_thread,
        args=(minutes, message),
        daemon=False,           # <-- THE CRITICAL CHANGE
    )
    thread.start()

    # Register in the tracker so we (and the user) can inspect it later
    with _reminders_lock:
        _active_reminders.append({
            "thread":   thread,
            "fires_at": fires_at,
            "message":  message,
        })

    return f"🔔 Reminder locked in! I'll alert you at {fires_at}: \"{message}\""


# ─── SMART REMINDER PARSER ────────────────────────────────────────────────────

# Common time words → minutes
_TIME_WORDS = {
    "half an hour": 30, "half hour": 30,
    "an hour": 60,      "a hour": 60,
    "quarter hour": 15, "quarter of an hour": 15,
}

def smart_reminder_parser(raw_text: str) -> str:
    """
    Fallback parser for natural-language reminder phrases.

    Called when the main intent router can't extract minutes/message cleanly.
    Handles patterns like:
        "remind me in 5 minutes to drink water"
        "remind me in half an hour"
        "set a reminder for 10 mins — check the oven"

    What you're learning:
    - Regex (re module) — pattern matching on text
    - Fallback / graceful degradation — never leave the user hanging
    - This is a tiny version of what NLU (Natural Language Understanding)
      systems do before routing to intent handlers
    """
    text = raw_text.lower().strip()

    # ── 1. Named time words ────────────────────────────────────────────────
    for phrase, mins in _TIME_WORDS.items():
        if phrase in text:
            msg = _extract_reminder_message(text)
            return set_reminder(mins, msg)

    # ── 2. "in X minutes / hours" pattern ─────────────────────────────────
    match = re.search(
        r"in\s+(\d+(?:\.\d+)?)\s*(min(?:ute)?s?|hr?s?|hours?)",
        text
    )
    if match:
        amount = float(match.group(1))
        unit   = match.group(2)
        mins   = int(amount * 60) if unit.startswith("h") else int(amount)
        msg    = _extract_reminder_message(text)
        return set_reminder(mins, msg)

    # ── 3. Bare number — assume minutes ───────────────────────────────────
    match = re.search(r"\b(\d+)\b", text)
    if match:
        mins = int(match.group(1))
        msg  = _extract_reminder_message(text)
        return set_reminder(mins, msg)

    return "❌ I couldn't figure out when to remind you. Try: 'remind me in 10 minutes to <task>'"


def _extract_reminder_message(text: str) -> str:
    """
    Pulls the 'what to remind about' part from a natural-language string.

    Looks for connectors like "to", "that", "about", "—" after the time part.
    Falls back to a generic message if nothing useful is found.
    """
    # Try "to <task>", "that <task>", "about <task>"
    match = re.search(r"\b(?:to|that|about)\b\s+(.+)$", text)
    if match:
        return match.group(1).strip().capitalize()

    # Try everything after a dash or colon
    match = re.search(r"[—\-:]\s*(.+)$", text)
    if match:
        return match.group(1).strip().capitalize()

    return "You set a reminder!"


# ─── DAILY SCHEDULE ───────────────────────────────────────────────────────────

def show_schedule():
    """
    Shows a suggested daily schedule for an engineering student.
    Customize this to match YOUR routine!
    
    What you're learning:
    - Multi-line strings and formatting
    - This is also a great intro to data-driven design
    """
    schedule = """
╔══════════════════════════════════════╗
║       📅  DAILY SCHEDULE            ║
╚══════════════════════════════════════╝

  🌅 MORNING
     06:00 — Wake up, freshen up
     06:30 — Exercise / Yoga (30 min)
     07:00 — Breakfast
     07:30 — Review yesterday's notes

  📚 STUDY BLOCK 1
     08:00 — College classes
     12:00 — Lunch break

  📚 STUDY BLOCK 2
     13:00 — College classes / Lab
     16:00 — Break & snack

  💻 CODING TIME
     16:30 — PANDA project / Python practice
     18:30 — DSA / Competitive programming

  🌙 EVENING
     19:00 — Dinner
     19:30 — Revision / Assignment work
     21:00 — Free time / Hobbies
     22:00 — Plan tomorrow, sleep!

  💡 TIP: Use 'timer 25' for 25-min Pomodoro sessions!
"""
    return schedule.strip()