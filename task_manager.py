"""
✨ PANDA — Task Manager Module
================================
This module handles your to-do list and quick notes.
Everything is saved to disk so it persists between sessions!

What you're learning here:
- JSON — the universal data format (used by every API)
- File I/O — reading and writing files
- CRUD operations — Create, Read, Update, Delete
- List comprehensions — Python's powerful one-liner loops
- Context managers — `with open()` for safe file handling
"""

import json
import os
import datetime
import threading
import time
import tkinter as tk
from tkinter import messagebox
import memory_manager

try:
    import voice
    _VOICE_AVAILABLE = True
except ImportError:
    _VOICE_AVAILABLE = False


# ─── FILE PATHS ───────────────────────────────────────────────────────────────
# Get the directory where this script lives, then point to data/

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TODOS_FILE = os.path.join(DATA_DIR, "todos.json")
NOTES_FILE = os.path.join(DATA_DIR, "notes.txt")


def _ensure_data_dir():
    """Creates the data directory if it doesn't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# MIGRATION ROUTINE
# ═══════════════════════════════════════════════════════════════════════════════

def _migrate_todos_to_db():
    """Migrates existing todos from the JSON file to the SQLite database."""
    if os.path.exists(TODOS_FILE):
        try:
            with open(TODOS_FILE, "r", encoding="utf-8") as f:
                todos = json.load(f)
            if isinstance(todos, list):
                for todo in todos:
                    if isinstance(todo, dict):
                        task = todo.get("task") or todo.get("title") or ""
                        done = 1 if todo.get("done") or todo.get("completed") else 0
                        created_at = todo.get("created") or todo.get("created_at")
                        deadline = todo.get("deadline")
                        reminder_mins = todo.get("reminder_minutes_before", 15)
                        if task:
                            memory_manager.save_todo(
                                task=task,
                                deadline=deadline,
                                reminder_minutes_before=reminder_mins,
                                done=done,
                                created_at=created_at
                            )
            # Rename file to back up and indicate migration done
            backup_path = TODOS_FILE + ".bak"
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.rename(TODOS_FILE, backup_path)
            print("  [TaskManager] Migrated existing todos to SQLite database successfully.")
        except Exception as e:
            print(f"  [TaskManager] Warning: failed to migrate todos: {e}")


# Run migration automatically when task_manager is loaded
_migrate_todos_to_db()


def add_todo(task, deadline=None, reminder_minutes_before=15):
    """
    Adds a new task to the database to-do list.
    """
    if not task.strip():
        return "❌ Please provide a task! Usage: todo add <task>"
    
    try:
        reminder_minutes_before = int(reminder_minutes_before) if reminder_minutes_before else 15
    except ValueError:
        reminder_minutes_before = 15

    deadline_val = deadline.strip() if (deadline and isinstance(deadline, str)) else None
    
    memory_manager.save_todo(task.strip(), deadline_val, reminder_minutes_before)
    
    msg = f"✅ Added task: {task.strip()}"
    if deadline_val:
        msg += f" (due: {deadline_val}, remind {reminder_minutes_before}m before)"
    return msg


def show_todos():
    """
    Displays all tasks with checkboxes from the DB.
    """
    todos = memory_manager.load_all_todos()
    
    if not todos:
        return "📋 Your to-do list is empty! Use 'todo add <task>' to add one."
    
    result = []
    result.append("╔══════════════════════════════════════╗")
    result.append("║          📋  TO-DO LIST              ║")
    result.append("╚══════════════════════════════════════╝")
    result.append("")
    
    for i, todo in enumerate(todos, 1):
        checkbox = "☑️" if todo["done"] else "⬜"
        status = " (done!)" if todo["done"] else ""
        due_info = f" [Due: {todo['deadline']}]" if todo["deadline"] else ""
        result.append(f"  {i}. {checkbox}  {todo['task']}{due_info}{status}")
    
    # Stats
    total = len(todos)
    done = sum(1 for t in todos if t["done"])
    result.append("")
    result.append(f"  📊 {done}/{total} completed")
    
    return "\n".join(result)


def complete_todo(number):
    """
    Marks a task as complete in the DB.
    """
    try:
        index = int(number) - 1
    except ValueError:
        return "❌ Please provide a valid task number! Usage: todo done <number>"
    
    todos = memory_manager.load_all_todos()
    
    if index < 0 or index >= len(todos):
        return f"❌ Invalid task number. You have {len(todos)} tasks."
    
    todo = todos[index]
    if todo["done"]:
        return f"ℹ️  Task #{number} is already complete!"
    
    memory_manager.complete_todo_db(todo["id"])
    return f"🎉 Completed: {todo['task']}"


def remove_todo(number):
    """
    Removes a specific task from the DB.
    """
    try:
        index = int(number) - 1
    except ValueError:
        return "❌ Please provide a valid task number! Usage: todo remove <number>"
    
    todos = memory_manager.load_all_todos()
    
    if index < 0 or index >= len(todos):
        return f"❌ Invalid task number. You have {len(todos)} tasks."
    
    todo = todos[index]
    memory_manager.remove_todo_db(todo["id"])
    return f"🗑️ Removed: {todo['task']}"


def clear_completed():
    """
    Removes all completed tasks from the DB.
    """
    removed_count = memory_manager.clear_completed_todos_db()
    if removed_count == 0:
        return "ℹ️  No completed tasks to clear."
    return f"🧹 Cleared {removed_count} completed task(s)!"


def show_unignorable_popup(title, message):
    """Spawns an unignorable tkinter popup window in a separate thread."""
    def _run_gui():
        root = tk.Tk()
        root.title(title)
        root.attributes("-topmost", True)
        
        # Center the window on screen
        root.update_idletasks()
        width = 450
        height = 180
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.configure(bg="#1e1e2e")
        root.resizable(False, False)

        # Style elements matching PANDA's color scheme
        title_font = ("Segoe UI", 12, "bold")
        msg_font = ("Segoe UI", 10)
        btn_font = ("Segoe UI", 10, "bold")

        lbl_hdr = tk.Label(root, text=title, font=title_font, fg="#f38ba8", bg="#1e1e2e", pady=8)
        lbl_hdr.pack()

        lbl_msg = tk.Label(root, text=message, font=msg_font, fg="#cdd6f4", bg="#1e1e2e", wraplength=400, pady=10)
        lbl_msg.pack()

        btn_ok = tk.Button(
            root, text="ACKNOWLEDGE", font=btn_font, bg="#a6e3a1", fg="#11111b",
            activebackground="#89b4fa", command=root.destroy, padx=20, pady=4, borderwidth=0
        )
        btn_ok.pack(pady=10)

        # Ensure it stays on top continuously and grabs focus
        root.focus_force()
        root.mainloop()

    # Start Tkinter GUI thread
    threading.Thread(target=_run_gui, daemon=True).start()


def start_deadline_checker():
    """Starts the background thread that checks for upcoming todo deadlines."""
    def _checker_loop():
        # Wait a bit on startup
        time.sleep(5)
        while True:
            try:
                upcoming = memory_manager.get_upcoming_deadlines()
                for todo in upcoming:
                    msg = f"Task deadline approaching: \"{todo['task']}\" due at {todo['deadline']}!"
                    
                    # 1. Speak aloud
                    if _VOICE_AVAILABLE:
                        try:
                            voice.speak(msg)
                        except Exception as e:
                            print(f"\n[Voice Error] Failed to speak: {e}")
                    
                    # 2. Show the unignorable topmost popup
                    show_unignorable_popup("⏰ PANDA Task Deadline Alert", msg)
                    
                    # Print to console as well
                    print(f"\n\n  🔔 ══════════════════════════════════════")
                    print(f"  🔔  DEADLINE ALERT: {msg}")
                    print(f"  🔔 ══════════════════════════════════════\n")
                    
                    # 3. Mark as reminded in the DB
                    memory_manager.mark_todo_reminded(todo["id"])
                    
            except Exception as e:
                print(f"[Deadline Checker Error] {e}")
            
            # Poll every 60 seconds
            time.sleep(60)

    checker_thread = threading.Thread(target=_checker_loop, daemon=False)
    checker_thread.start()


# ═══════════════════════════════════════════════════════════════════════════════
# QUICK NOTES
# ═══════════════════════════════════════════════════════════════════════════════

def save_note(text):
    """
    Appends a note to the notes file with a timestamp.
    
    What you're learning:
    - File append mode ("a") vs write mode ("w")
    - Append adds to the end, write overwrites everything
    """
    if not text.strip():
        return "❌ Please provide a note! Usage: note <text>"
    
    _ensure_data_dir()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {text.strip()}\n")
    
    return f"📝 Note saved: {text.strip()}"


def show_notes():
    """
    Displays all saved notes.
    
    What you're learning:
    - File reading with error handling
    - Checking if a file exists before reading
    """
    if not os.path.exists(NOTES_FILE):
        return "📝 No notes yet! Use 'note <text>' to save one."
    
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except IOError:
        return "❌ Couldn't read notes file."
    
    if not content:
        return "📝 No notes yet! Use 'note <text>' to save one."
    
    result = []
    result.append("╔══════════════════════════════════════╗")
    result.append("║          📝  YOUR NOTES              ║")
    result.append("╚══════════════════════════════════════╝")
    result.append("")
    
    for line in content.split("\n"):
        if line.strip():
            result.append(f"  {line}")
    
    return "\n".join(result)


def clear_notes():
    """
    Deletes all notes.
    
    What you're learning:
    - File write mode ("w") with empty string = clear file
    - os.path.exists for checking files
    """
    if os.path.exists(NOTES_FILE):
        with open(NOTES_FILE, "w") as f:
            f.write("")
        return "🗑️ All notes cleared!"
    return "ℹ️  No notes to clear."
