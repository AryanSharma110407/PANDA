import os

file_path = r"d:\Aryan\Alya testing\smart_brain.py"
with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Lines are 1-indexed. We want to comment out lines 491 to 927 (0-indexed: 490 to 926).
start_idx = 490
end_idx = 927 # up to line 927 inclusive (0-indexed 926)

for idx in range(start_idx, end_idx):
    if idx < len(lines):
        line = lines[idx]
        if not line.strip().startswith("#"):
            lines[idx] = "# " + line

# Add dummy stubs at the end of the file or right after the commented section
stubs = """

# Dummy NLU stubs to prevent import errors in alya.py
class SmartBrain:
    def __init__(self):
        pass
    def process(self, user_input):
        return None

def _is_question(user_input, has_conversation_history=False):
    return False
"""

# Let's insert stubs right after the commented block
lines.insert(end_idx, stubs)

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("NLU architecture commented out successfully!")
