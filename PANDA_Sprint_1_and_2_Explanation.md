# PANDA Project: Sprint 1 & Sprint 2 Changes

This document explains the changes made during Sprint 1 and Sprint 2 of the PANDA project in simple words. It covers the theory behind the changes and how they were implemented in the code.

---

## Sprint 1: Smart Memory and RAG (Retrieval-Augmented Generation)

### The Theory (Simple Explanation)
Before Sprint 1, PANDA had a basic "passive" memory. It could remember the current conversation, but it didn't really "understand" it or recall relevant things from the past automatically. 

Sprint 1 introduced **RAG (Retrieval-Augmented Generation)**. Think of this as giving PANDA a searchable, intelligent brain. When you say something, PANDA converts your sentence into a "vector embedding" (a list of numbers that represents the actual *meaning* of your sentence).

When you ask a question later, PANDA compares the meaning of your question against all its stored memories and instantly retrieves the most relevant past conversations to help it answer better. We also added an **"importance score"** so PANDA knows that career goals are more important to remember than casual greetings.

### The Code Changes

**1. New Database Tables (`memory_manager.py`)**  
We created two new tables: `interactions` (to store exactly what you and PANDA said) and `vector_memory` (to store the mathematical meaning/embeddings of those messages so they can be searched later).

**2. The Brain of Memory (`vector_memory.py`)**  
We created a brand new file to handle the heavy lifting. It converts text to vectors using a local AI model, calculates the importance score (e.g., 0.95 for goals, 0.05 for 'hello'), and performs the 'semantic search' to find the most relevant memories based on meaning, not just exact keywords.

**3. Automatic Context (`smart_brain.py`)**  
We updated PANDA's thinking process. Now, before PANDA answers you, it silently searches its vector memory for relevant past conversations and injects them into its instructions. This allows PANDA to reference past discussions naturally without you having to remind it.

**4. Search Command (`alya.py`)**  
We added a new command so you can type `search memory <query>` in the terminal to manually see what PANDA remembers about any topic.

---

## Sprint 2: Structured Entities (Goals and Projects)

### The Theory (Simple Explanation)
Now that PANDA could remember general conversations, Sprint 2 focused on making it understand specific, important things: **Goals** and **Projects**. 

Instead of just treating a goal like normal chat text, we wanted PANDA to explicitly track it. We gave Goals and Projects a higher priority in memory. We also added a **"mention count"** — every time a new conversation relates to an existing goal or project, PANDA dynamically increases its mention count, signaling that this topic is actively being worked on and is highly relevant.

### The Code Changes

**1. Goal and Project Tables (`memory_manager.py`)**  
We added `goals` and `projects` tables to the database to explicitly store their status (e.g., active, completed), mention counts, and creation times. We also added a function to mark a goal as completed once you achieve it.

**2. Smart Saving & Caching (`vector_memory.py`)**  
We added functions to properly save goals and projects into the vector memory so they can be searched. We also built an **'embedding cache'**. Because checking every new message against all goals to update the mention count is computationally expensive, the cache remembers the math vectors for goals and projects so PANDA stays fast without recalculating everything constantly.

**3. Understanding New Commands (`alya.py` & `fusion_layer.py`)**  
We updated PANDA's command list and internal logic so it understands new commands like: `add a goal`, `show goals`, `complete goal 1`, `add a project`, and `show projects`. We also made sure that when you run these commands, the action is synced to PANDA's short-term memory so it has the context of what just happened.
