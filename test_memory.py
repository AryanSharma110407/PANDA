"""
PANDA Memory System — Test Suite (Step 15)
============================================
Validates all 5 test cases before moving to Phase 2.

Tests:
  TEST 1 — Startup restoration ("what were we talking about?")
  TEST 2 — Persistence across reboot (data survives restart)
  TEST 3 — Conversation ordering (chronological correctness)
  TEST 4 — Memory loads quickly (performance)
  TEST 5 — LLM receives proper context (Ollama-ready format)
"""

import time
import os
import sys

# Ensure we can import from the project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_manager
from memory import ConversationManager, _estimate_tokens, _trim_to_token_budget

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []


def test(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append(condition)
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")
    if not condition:
        print(f"         \033[31m^ FAILED\033[0m")


print("\n" + "=" * 60)
print("  PANDA Memory System — Test Suite (Step 15)")
print("=" * 60)


# ═══════════════════════════════════════════════════════════════════════════════
# SETUP — Clean slate for testing
# ═══════════════════════════════════════════════════════════════════════════════
print("\n  [Setup] Initializing database...")
memory_manager.initialize_memory()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Startup Restoration
# "Close PANDA, reopen PANDA, ask what were we talking about?"
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 1: Startup Restoration ---")

# Simulate Session A (first launch)
conv_a = ConversationManager()
conv_a.initialize()
session_a = conv_a.get_session_id()

conv_a.save_turn("tell me about machine learning", "Machine learning is a subset of AI that learns from data...")
conv_a.save_turn("how does neural network work?", "A neural network mimics the brain using layers of nodes...")
conv_a.save_turn("what about transformers?", "Transformers use self-attention mechanisms for sequence data...")
print(f"  Session A: {session_a} (3 turns saved)")

# Simulate PANDA restart — create a BRAND NEW ConversationManager
# This is exactly what happens when alya.py restarts
conv_b = ConversationManager()
conv_b.initialize()
session_b = conv_b.get_session_id()

# Verify: new session ID is different
test("New session ID generated",
     session_b != session_a,
     f"A={session_a}, B={session_b}")

# Verify: startup context mentions last session's topics
startup = conv_b.get_startup_context()
test("Startup context is not empty",
     len(startup) > 0,
     f'Got: "{startup[:80]}..."')

test("Startup context mentions previous topics",
     "machine learning" in startup.lower() or "neural" in startup.lower() or "transformer" in startup.lower(),
     f'Looking for ML/neural/transformer in: "{startup[:80]}"')


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2 — Persistence Across Reboot
# "Conversation persists across reboot"
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 2: Persistence Across Reboot ---")

# Save messages in current session
conv_b.save_turn("what is Python?", "Python is a high-level programming language...")

# Simulate FULL restart — new manager, new session
conv_c = ConversationManager()
conv_c.initialize()

# Verify old sessions still exist in the database
old_messages = memory_manager.load_session_messages(session_a, limit=10)
test("Session A data persists after restart",
     len(old_messages) == 6,  # 3 turns = 6 messages
     f"Expected 6 messages, got {len(old_messages)}")

old_messages_b = memory_manager.load_session_messages(session_b, limit=10)
test("Session B data persists after restart",
     len(old_messages_b) == 2,  # 1 turn = 2 messages
     f"Expected 2 messages, got {len(old_messages_b)}")

# Verify content integrity
test("Message content is intact",
     old_messages[0]["content"] == "tell me about machine learning",
     f'Got: "{old_messages[0]["content"][:50]}"')


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3 — Conversation Ordering
# "Conversation ordering remains correct"
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 3: Conversation Ordering ---")

# Save numbered messages to verify order
conv_c_sid = conv_c.get_session_id()
for i in range(1, 6):
    conv_c.save_turn(f"message {i}", f"response {i}")

context = conv_c.get_context()
test("Context is not empty",
     len(context) > 0,
     f"Got {len(context)} messages")

# Verify chronological order
user_messages = [m["content"] for m in context if m["role"] == "user"]
expected_order = [f"message {i}" for i in range(1, 6)]
test("Messages are in chronological order",
     user_messages == expected_order,
     f"Order: {user_messages}")

# Verify alternation: user, assistant, user, assistant...
roles = [m["role"] for m in context]
alternating = all(
    roles[i] != roles[i+1]
    for i in range(len(roles) - 1)
)
test("Roles alternate correctly (user/assistant/user/assistant)",
     alternating,
     f"Roles: {roles}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4 — Memory Loads Quickly
# "Memory loads quickly"
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 4: Performance ---")

# Add more data to stress test
for i in range(50):
    memory_manager.save_message(conv_c_sid, "user", f"stress test question {i}")
    memory_manager.save_message(conv_c_sid, "assistant", f"stress test answer {i} " * 20)

# Time the load operation
start = time.perf_counter()
for _ in range(100):  # 100 consecutive loads
    context = conv_c.get_context()
elapsed = time.perf_counter() - start

avg_ms = (elapsed / 100) * 1000
test(f"100 context loads completed",
     True,
     f"Total: {elapsed:.3f}s, Average: {avg_ms:.1f}ms per load")

test(f"Average load time < 50ms",
     avg_ms < 50,
     f"Got {avg_ms:.1f}ms (limit: 50ms)")

# Verify trimming worked (shouldn't return all 110 messages)
test("Context is trimmed (not returning entire DB)",
     len(context) <= 20,
     f"Got {len(context)} messages (max 20)")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5 — LLM Receives Proper Context
# "LLM receives proper context" — Ollama-ready format
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- TEST 5: LLM Context Format ---")

# Create a fresh session for clean testing
conv_d = ConversationManager()
conv_d.initialize()

conv_d.save_turn("hello", "Hi there!")
conv_d.save_turn("what is 2+2?", "That would be 4.")

context = conv_d.get_context()

# Verify it's a list
test("Context is a list",
     isinstance(context, list),
     f"Type: {type(context)}")

# Verify each message is a dict with 'role' and 'content'
all_valid = all(
    isinstance(m, dict) and "role" in m and "content" in m
    for m in context
)
test("Every message has 'role' and 'content' keys",
     all_valid,
     f"Sample: {context[0] if context else 'empty'}")

# Verify roles are only 'user' or 'assistant'
valid_roles = all(m["role"] in ("user", "assistant") for m in context)
test("All roles are 'user' or 'assistant'",
     valid_roles,
     f"Roles: {[m['role'] for m in context]}")

# Verify content is strings
valid_content = all(isinstance(m["content"], str) for m in context)
test("All content values are strings",
     valid_content)

# Verify token trimming works
big_messages = [
    {"role": "user", "content": "x" * 10000},
    {"role": "assistant", "content": "y" * 10000},
    {"role": "user", "content": "z" * 10000},
    {"role": "assistant", "content": "w" * 10000},
    {"role": "user", "content": "important question"},
    {"role": "assistant", "content": "important answer"},
]
trimmed = _trim_to_token_budget(list(big_messages), max_tokens=100)
test("Token trimming removes oldest when over budget",
     len(trimmed) < len(big_messages),
     f"Before: {len(big_messages)} msgs, After: {len(trimmed)} msgs")

test("Token trimming keeps at least 2 messages",
     len(trimmed) >= 2,
     f"Kept {len(trimmed)} messages")

# Verify filtered content doesn't get saved
conv_d.save_turn("", "")  # blank
conv_d.save_turn("   ", "   ")  # whitespace
conv_d.save_turn("[DEBUG] test", "normal reply")  # debug noise
context_after = conv_d.get_context()
debug_in_context = any("[DEBUG]" in m["content"] for m in context_after)
test("Filtered content (blanks, debug) not in context",
     not debug_in_context,
     f"Messages after filtering: {len(context_after)}")


# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
passed = sum(results)
total = len(results)
if passed == total:
    print(f"  \033[32m ALL {total} TESTS PASSED \033[0m")
else:
    print(f"  \033[31m {passed}/{total} TESTS PASSED ({total - passed} FAILED) \033[0m")
print("=" * 60 + "\n")
