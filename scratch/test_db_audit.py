"""
Audit script: Tests that lessons & preferences are saved/loaded correctly,
and that they get injected into the LLM system prompt.
"""
import sys
sys.path.insert(0, ".")

import memory_manager
memory_manager.initialize_memory()

print("=" * 60)
print("TEST 1: save_lesson & load_lessons")
print("=" * 60)
lid = memory_manager.save_lesson("test_audit", "When copying text from AnyDesk, use right-click instead of system_search.", 0.8)
print(f"  Saved lesson ID: {lid}")

lessons = memory_manager.load_lessons(limit=5)
print(f"  Loaded {len(lessons)} lesson(s):")
for l in lessons:
    lesson_id = l.get("id")
    lesson_txt = l.get("lesson_text", "")
    print(f"    - [ID={lesson_id}] {lesson_txt[:80]}")

print()
print("=" * 60)
print("TEST 2: save_preference & load_preferences")
print("=" * 60)
pid = memory_manager.save_preference("test_audit", "Never close the browser window after completing a task.")
print(f"  Saved preference ID: {pid}")

prefs = memory_manager.load_preferences()
print(f"  Loaded {len(prefs)} preference(s):")
for p in prefs:
    pref_id = p.get("id")
    pref_txt = p.get("preference_text", "")
    print(f"    - [ID={pref_id}] {pref_txt[:80]}")

print()
print("=" * 60)
print("TEST 3: Lessons & Preferences injected into system prompt")
print("=" * 60)
from action.task_prompts import get_agent_system_prompt
prompt = get_agent_system_prompt()

if "LESSONS LEARNED" in prompt:
    print("  OK - 'LESSONS LEARNED' section found in system prompt")
else:
    print("  FAIL - 'LESSONS LEARNED' section NOT found in system prompt")

if "When copying text from AnyDesk" in prompt:
    print("  OK - Test lesson text found in system prompt")
else:
    print("  FAIL - Test lesson text NOT found in system prompt")

if "Never close the browser window" in prompt:
    print("  OK - Test preference text found in system prompt")
else:
    print("  FAIL - Test preference text NOT found in system prompt")

# Print the first 800 chars of the prompt so we can see the injection
print()
print("=" * 60)
print("SYSTEM PROMPT (first 800 chars):")
print("=" * 60)
print(prompt[:800])

print()
print("=" * 60)
print("TEST 4: build_rich_task_context includes preferences")
print("=" * 60)
from action.task_executor import build_rich_task_context
ctx = build_rich_task_context("Test task", "test_audit")
if "Never close the browser window" in ctx:
    print("  OK - Preference found in rich task context")
else:
    print("  FAIL - Preference NOT found in rich task context")

print()
print("ALL AUDIT TESTS COMPLETE")
