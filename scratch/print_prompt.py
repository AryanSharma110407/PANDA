import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from action.task_prompts import get_agent_system_prompt

def main():
    prompt = get_agent_system_prompt()
    print("--- SYSTEM PROMPT ---")
    print(prompt)
    print("---------------------")

if __name__ == "__main__":
    main()
