"""
P.A.N.D.A. — Mark IV
==========================
Proactive Autonomous Neural Directive Agent
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.system("")   # Enable ANSI on Windows

env_path = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=env_path)

if os.getenv("HF_TOKEN"):
    os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")

print("🤖 HF token loaded:", bool(os.getenv("HF_TOKEN")))
print(f"🧠 Ollama target:   {OLLAMA_URL}")
print(f"🧠 Model:           {MODEL_NAME}")

os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

import logging
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

if __name__ == "__main__":
    from command_dispatcher import ensure_ollama_running, main
    ensure_ollama_running()
    main()
