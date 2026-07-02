import re

def extract_time_phrase(text):
    # Try to extract time-related part
    match = re.search(r"(at\s+.*|in\s+.*|tomorrow.*|next.*)", text.lower())
    
    if match:
        return match.group(0)

    return text  # fallback


import dateparser

user_input = "remind me at 2:00 AM"

time_text = extract_time_phrase(user_input)
dt = dateparser.parse(time_text)

print(time_text)  # DEBUG
print(dt)