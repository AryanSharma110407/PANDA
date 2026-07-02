import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path and load env
project_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_dir))
load_dotenv(dotenv_path=project_dir / ".env")

from action.macro_planner import generate_macro_plan

def test_notepad_task():
    print("\n==============================================")
    print("TEST: 'open notepad and write a letter for me to school'")
    print("==============================================")
    
    # 1. First analysis of vague task
    task_desc = "open notepad and write a letter for me to school"
    print(f"Goal: {task_desc}")
    plan = generate_macro_plan(task_desc)
    print("Planner response:")
    import pprint
    pprint.pprint(plan)
    
    # Check that it asks for letter content but DOES NOT ask for email address
    missing = plan.get("missing_variables", [])
    print(f"Missing variables: {missing}")
    print(f"Clarification question: '{plan.get('clarification_question')}'")
    
    # 2. Simulate user clarifying the contents
    task_desc += "\nUser clarified: The letter should say that I need 2 days off for sick leave."
    print(f"\nClarified Goal: {task_desc}")
    plan2 = generate_macro_plan(task_desc)
    print("Planner response after clarification:")
    pprint.pprint(plan2)
    print(f"Missing variables: {plan2.get('missing_variables')}")
    print(f"Locked Path: {plan2.get('path')}")

def test_whatsapp_search_task():
    print("\n==============================================")
    print("TEST: 'message arnav on whatsapp i'll be late for tomorrow's game'")
    print("==============================================")
    
    # 1. First analysis of task
    task_desc = "message arnav on whatsapp i'll be late for tomorrow's game"
    print(f"Goal: {task_desc}")
    plan = generate_macro_plan(task_desc)
    print("Planner response:")
    import pprint
    pprint.pprint(plan)
    
    # 2. Simulate user saying to search contact instead of providing a number
    task_desc += "\nUser clarified: just search for Arnab in my whatsapp contact list, it's saved"
    print(f"\nClarified Goal: {task_desc}")
    plan2 = generate_macro_plan(task_desc)
    print("Planner response after clarification:")
    pprint.pprint(plan2)
    print(f"Missing variables: {plan2.get('missing_variables')}")
    print(f"Locked Path: {plan2.get('path')}")

if __name__ == "__main__":
    test_notepad_task()
    test_whatsapp_search_task()
