"""
Cleanup script: Remove garbage JSON blobs from lessons and preferences tables.
These were created by test mocks that echoed raw action JSON instead of natural language.
"""
import sys
sys.path.insert(0, ".")

import memory_manager

conn = memory_manager._get_connection()
cursor = conn.cursor()

# Count garbage lessons (start with '{' or '[')
cursor.execute("SELECT id, lesson_text FROM lessons WHERE lesson_text LIKE '{%' OR lesson_text LIKE '[%'")
garbage_lessons = cursor.fetchall()
print(f"Found {len(garbage_lessons)} garbage lesson(s) to delete:")
for row in garbage_lessons:
    print(f"  - [ID={row['id']}] {row['lesson_text'][:60]}...")

# Delete them
if garbage_lessons:
    cursor.execute("DELETE FROM lessons WHERE lesson_text LIKE '{%' OR lesson_text LIKE '[%'")
    print(f"  Deleted {cursor.rowcount} garbage lessons.")

# Count garbage preferences (start with '{' or '[')
cursor.execute("SELECT id, preference_text FROM preferences WHERE preference_text LIKE '{%' OR preference_text LIKE '[%'")
garbage_prefs = cursor.fetchall()
print(f"\nFound {len(garbage_prefs)} garbage preference(s) to delete:")
for row in garbage_prefs:
    print(f"  - [ID={row['id']}] {row['preference_text'][:60]}...")

# Delete them
if garbage_prefs:
    cursor.execute("DELETE FROM preferences WHERE preference_text LIKE '{%' OR preference_text LIKE '[%'")
    print(f"  Deleted {cursor.rowcount} garbage preferences.")

conn.commit()
conn.close()

print("\nCleanup complete. Verifying...")

# Verify
lessons = memory_manager.load_lessons(limit=10)
print(f"\nRemaining lessons ({len(lessons)}):")
for l in lessons:
    print(f"  - [ID={l.get('id')}] {l.get('lesson_text', '')[:80]}")

prefs = memory_manager.load_preferences()
print(f"\nRemaining preferences ({len(prefs)}):")
for p in prefs:
    print(f"  - [ID={p.get('id')}] {p.get('preference_text', '')[:80]}")
