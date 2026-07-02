"""
✨ PANDA — Memory Graph Visualizer
===================================
Constructs ephemeral NetworkX graphs from SQLite memory layers and exports
them as interactive visual representations (HTML/JSON).

NetworkX is used strictly as a structural processing layer, NEVER as primary persistence.
"""

import os
import json
import networkx as nx
import memory_manager

# Color definitions for different memory types
COLOR_MAP = {
    "goals": "#10B981",        # Emerald Green
    "projects": "#3B82F6",     # Neon Blue
    "preferences": "#F59E0B",  # Amber/Gold
    "corrections": "#EF4444",  # Hot Pink/Red
    "interactions": "#8B5CF6", # Purple
    "reflections": "#EC4899",  # Magenta/Pink
    "goal_steps": "#06B6D4"    # Cyan
}


# Minimum importance score for showing interactions in the graph.
# Raise this to reduce clutter; lower it to show more memory threads.
INTERACTION_IMPORTANCE_THRESHOLD = 0.50
GOAL_IMPORTANCE_THRESHOLD = 0.10
MAX_NODES = 350  # Safety cap — D3 freezes above ~500 nodes


def get_node_details(table: str, ids: list[int], interaction_threshold: float = INTERACTION_IMPORTANCE_THRESHOLD) -> dict[int, dict]:
    """
    Queries SQLite to fetch records for specific IDs in a table.
    Filters out consolidated, abandoned, or heavily decayed memories.
    Pass interaction_threshold=0.0 to get all interactions regardless of score.
    """
    if not ids:
        return {}
    if table not in ["goals", "projects", "preferences", "corrections", "interactions", "reflections"]:
        return {}

    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in ids)
    try:
        query = f"SELECT * FROM {table} WHERE id IN ({placeholders})"
        if table in ["goals", "projects", "preferences"]:
            query += f" AND consolidated_to IS NULL AND importance_score >= {GOAL_IMPORTANCE_THRESHOLD}"
            if table == "goals":
                query += " AND status != 'abandoned'"
        elif table == "interactions":
            if interaction_threshold > 0.0:
                query += f" AND importance_score >= {interaction_threshold}"
            # if threshold is 0.0 — no filter, return everything
        elif table == "reflections":
            query += f" AND importance_score >= {GOAL_IMPORTANCE_THRESHOLD}"
            
        cursor.execute(query, ids)
        rows = cursor.fetchall()
        return {row["id"]: dict(row) for row in rows}
    except Exception as e:
        print(f"  [GraphVisualizer] Error fetching details for {table}: {e}")
        return {}
    finally:
        conn.close()


def build_networkx_graph(interaction_threshold: float = INTERACTION_IMPORTANCE_THRESHOLD) -> nx.DiGraph:
    """
    Reads all nodes and edges (links) from SQLite and constructs an ephemeral NetworkX DiGraph.
    Includes reflections, hierarchical goal steps, semantic links AND synthetic neural connections
    so the graph always looks like a richly connected brain — not isolated dots.

    interaction_threshold: minimum importance_score for interactions to be included.
        Use INTERACTION_IMPORTANCE_THRESHOLD (default) for the fast/filtered view.
        Use 0.0 to load every interaction — the full deep-memory view.
    """
    G = nx.DiGraph()

    # 1. Fetch all semantic links from the database
    semantic_links = memory_manager.get_all_links()

    # 2. Load all node IDs from every table
    by_table = {}
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    for table in ["goals", "projects", "preferences", "corrections", "interactions", "reflections"]:
        try:
            cursor.execute(f"SELECT id FROM {table}")
            by_table[table] = [row["id"] for row in cursor.fetchall()]
        except Exception:
            pass

    # Ensure active goals are included
    conn2 = memory_manager._get_connection()
    cursor2 = conn2.cursor()
    try:
        cursor2.execute("SELECT id FROM goals WHERE status = 'active' AND consolidated_to IS NULL")
        active_goals = [dict(row) for row in cursor2.fetchall()]
        active_ids_set = set(by_table.setdefault("goals", []))
        for g in active_goals:
            if g["id"] not in active_ids_set:
                by_table["goals"].append(g["id"])
    except Exception as e:
        print(f"  [GraphVisualizer] Error ensuring active goals in graph: {e}")
        active_goals = []
    finally:
        conn2.close()

    # 3. Fetch full record details for all nodes
    node_details = {}
    for table, ids in by_table.items():
        node_details[table] = get_node_details(table, ids, interaction_threshold=interaction_threshold)

    # 4. Add nodes to graph
    # Track session_id -> [node_keys] for session-based neural wiring
    session_buckets: dict[str, list[str]] = {}

    for table, ids in by_table.items():
        for node_id in ids:
            details = node_details.get(table, {}).get(node_id)
            if not details:
                continue

            label = f"{table}:{node_id}"
            content = ""
            importance = details.get("importance_score", 0.5)
            session_id = str(details.get("session_id") or "global")
            timestamp = details.get("created_at") or details.get("timestamp") or ""

            if table == "goals":
                content = details.get("goal_text", "")
                label = f"Goal: {content[:30]}..." if len(content) > 30 else f"Goal: {content}"
            elif table == "projects":
                proj_name = details.get("project_name", "")
                desc = details.get("description", "")
                content = f"{proj_name} - {desc}"
                label = f"Project: {proj_name}"
            elif table == "preferences":
                content = details.get("preference_text", "")
                label = f"Pref: {content[:30]}..." if len(content) > 30 else f"Pref: {content}"
            elif table == "corrections":
                mistake = details.get("mistake_context", "")
                fact = details.get("corrected_fact", "")
                content = f"Correction: Thought '{mistake}', but truth is '{fact}'"
                label = f"Corr: {fact[:30]}..." if len(fact) > 30 else f"Corr: {fact}"
            elif table == "interactions":
                user_msg = details.get("user_message", "")
                asst_resp = details.get("assistant_response", "")
                content = f"User: {user_msg}\nAssistant: {asst_resp}"
                label = f"Int: {user_msg[:30]}..." if len(user_msg) > 30 else f"Int: {user_msg}"
            elif table == "reflections":
                content = details.get("insight_text", "")
                label = f"Reflect: {content[:30]}..." if len(content) > 30 else f"Reflect: {content}"

            node_key = f"{table}:{node_id}"
            G.add_node(
                node_key,
                table=table,
                source_id=node_id,
                label=label,
                content=content,
                importance=importance,
                session_id=session_id,
                timestamp=timestamp,
                color=COLOR_MAP.get(table, "#9CA3AF")
            )

            # Track for session-based wiring
            session_buckets.setdefault(session_id, []).append(node_key)

    # Ensure explicitly-added active goals are in G
    for g in active_goals:
        goal_id = g["id"]
        goal_key = f"goals:{goal_id}"
        if not G.has_node(goal_key):
            details = node_details.get("goals", {}).get(goal_id)
            if details:
                content = details.get("goal_text", "")
                label = f"Goal: {content[:30]}..." if len(content) > 30 else f"Goal: {content}"
                sid = str(details.get("session_id") or "global")
                G.add_node(
                    goal_key,
                    table="goals",
                    source_id=goal_id,
                    label=label,
                    content=content,
                    importance=details.get("importance_score", 0.5),
                    session_id=sid,
                    timestamp=details.get("created_at") or "",
                    color=COLOR_MAP.get("goals", "#10B981")
                )
                session_buckets.setdefault(sid, []).append(goal_key)

    # 5. Load active goal steps with their connections
    try:
        active_goal_ids = [row["id"] for row in active_goals]
        goal_steps = []
        if active_goal_ids:
            placeholders = ",".join("?" for _ in active_goal_ids)
            cursor.execute(f"""
                SELECT s.* FROM goal_steps s
                JOIN goals g ON s.goal_id = g.id
                WHERE s.goal_id IN ({placeholders})
                  AND (g.current_plan_version = 0 OR s.plan_version = g.current_plan_version)
            """, active_goal_ids)
            goal_steps = [dict(row) for row in cursor.fetchall()]

        for step in goal_steps:
            step_id = step["id"]
            goal_id = step["goal_id"]
            step_text = step["step_text"]
            step_num = step["step_number"]
            status = step["status"]

            node_key = f"goal_steps:{step_id}"
            label = f"Step {step_num}: {step_text[:20]}..." if len(step_text) > 20 else f"Step {step_num}: {step_text}"
            content = f"Sub-step of Goal {goal_id}\nStatus: {status}\nText: {step_text}"

            G.add_node(
                node_key,
                table="goal_steps",
                source_id=step_id,
                label=label,
                content=content,
                importance=0.6,
                status=status,
                session_id="unknown",
                timestamp=step["created_at"],
                color=COLOR_MAP.get("goal_steps", "#06B6D4")
            )

            goal_key = f"goals:{goal_id}"
            if G.has_node(goal_key):
                G.add_edge(goal_key, node_key, weight=1.0, link_type="plan_step")

            dep_id = step.get("depends_on")
            if dep_id is not None:
                dep_key = f"goal_steps:{dep_id}"
                if G.has_node(dep_key):
                    G.add_edge(dep_key, node_key, weight=1.0, link_type="depends_on")
    except Exception as e:
        print(f"  [GraphVisualizer] Error loading goal steps for graph: {e}")
    finally:
        conn.close()

    # 6. Add semantic links from memory_links table
    for link in semantic_links:
        source_key = f"{link['source_table']}:{link['source_id']}"
        target_key = f"{link['target_table']}:{link['target_id']}"
        if G.has_node(source_key) and G.has_node(target_key):
            G.add_edge(
                source_key,
                target_key,
                weight=link["similarity_score"],
                link_type=link["link_type"]
            )

    # ── 7. SYNTHETIC NEURAL CONNECTIONS ──────────────────────────────────────
    # These create the "brain" look — nodes aren't isolated dots anymore.
    # We add session-based synaptic chains and cross-table importance bridges.

    # 7a. Session-based temporal chain: nodes in the same session fire together
    #     Connect sequential interactions within each session as a neural pathway
    for session_id, node_keys in session_buckets.items():
        if session_id in ("unknown", "global") or len(node_keys) < 2:
            continue

        # Sort by node type priority + node id for stable ordering
        def _sort_key(k):
            table, _, nid = k.partition(":")
            priority = {"interactions": 0, "reflections": 1, "preferences": 2,
                        "corrections": 3, "projects": 4, "goals": 5, "goal_steps": 6}
            return (priority.get(table, 9), int(nid) if nid.isdigit() else 0)

        sorted_keys = sorted(node_keys, key=_sort_key)

        # Build a chain: each node connects to the next (temporal synapse)
        for i in range(len(sorted_keys) - 1):
            src = sorted_keys[i]
            tgt = sorted_keys[i + 1]
            if not G.has_edge(src, tgt):
                src_imp = G.nodes[src].get("importance", 0.3)
                tgt_imp = G.nodes[tgt].get("importance", 0.3)
                weight = (src_imp + tgt_imp) / 2.0
                G.add_edge(src, tgt, weight=weight, link_type="session_synapse")

    # 7b. Interaction temporal chain: connect ALL interactions in chronological order
    #     (the main neural highway — conversations are how the brain formed)
    all_interaction_keys = [
        k for k in G.nodes() if k.startswith("interactions:")
    ]
    all_interaction_keys.sort(key=lambda k: int(k.split(":")[1]) if k.split(":")[1].isdigit() else 0)

    # Connect every interaction to the next 2 (forward temporal links)
    for i in range(len(all_interaction_keys) - 1):
        src = all_interaction_keys[i]
        tgt = all_interaction_keys[i + 1]
        if not G.has_edge(src, tgt):
            imp = G.nodes[src].get("importance", 0.3)
            G.add_edge(src, tgt, weight=imp, link_type="temporal")
        # Skip-1 connection for richer mesh (every 3rd node connects to 2 ahead)
        if i + 2 < len(all_interaction_keys) and i % 3 == 0:
            tgt2 = all_interaction_keys[i + 2]
            if not G.has_edge(src, tgt2):
                G.add_edge(src, tgt2, weight=0.3, link_type="temporal_skip")

    # 7c. Cross-table importance bridges:
    #     High-importance reflections wire to high-importance interactions in the same session
    #     Preferences, corrections, and goals each get wired into the interaction backbone
    reflection_keys = [k for k in G.nodes() if k.startswith("reflections:")]
    preference_keys = [k for k in G.nodes() if k.startswith("preferences:")]
    correction_keys = [k for k in G.nodes() if k.startswith("corrections:")]
    goal_keys = [k for k in G.nodes() if k.startswith("goals:")]
    project_keys = [k for k in G.nodes() if k.startswith("projects:")]

    def _wire_to_nearest_interactions(special_keys, max_per_node=3, link_type="semantic_bridge"):
        """Wire each special node to up to max_per_node nearby interactions by session or id proximity."""
        for sk in special_keys:
            s_node = G.nodes[sk]
            s_session = s_node.get("session_id", "global")
            # Prefer same-session interactions
            same_session = [
                ik for ik in all_interaction_keys
                if G.nodes[ik].get("session_id") == s_session
            ]
            pool = same_session if same_session else all_interaction_keys
            # Sort by importance desc and pick top N
            pool_sorted = sorted(pool, key=lambda k: G.nodes[k].get("importance", 0), reverse=True)
            for ik in pool_sorted[:max_per_node]:
                if not G.has_edge(sk, ik) and not G.has_edge(ik, sk):
                    imp = (G.nodes[sk].get("importance", 0.3) + G.nodes[ik].get("importance", 0.3)) / 2
                    G.add_edge(sk, ik, weight=imp, link_type=link_type)

    _wire_to_nearest_interactions(reflection_keys, max_per_node=4, link_type="reflection_synapse")
    _wire_to_nearest_interactions(preference_keys, max_per_node=3, link_type="preference_wire")
    _wire_to_nearest_interactions(correction_keys, max_per_node=3, link_type="correction_wire")
    _wire_to_nearest_interactions(goal_keys, max_per_node=5, link_type="goal_wire")
    _wire_to_nearest_interactions(project_keys, max_per_node=4, link_type="project_wire")

    total_edges = G.number_of_edges()
    total_nodes = G.number_of_nodes()
    print(f"  [GraphVisualizer] Neural graph built: {total_nodes} nodes, {total_edges} edges (synaptic connections)")
    return G


def export_graph_to_json(G: nx.DiGraph) -> dict:
    """
    Exports a NetworkX graph to a dictionary matching D3 node-link format.
    Applies a node cap to keep the browser from freezing on large graphs.
    """
    # edges='links' suppresses the NetworkX 3.6 FutureWarning
    data = nx.readwrite.json_graph.node_link_data(G, edges="links")
    # NetworkX 3+ uses different formats. Let's standardise the structure.
    all_nodes = []
    for node in data.get("nodes", []):
        all_nodes.append({
            "id": node.get("id"),
            "table": node.get("table"),
            "source_id": node.get("source_id"),
            "label": node.get("label"),
            "content": node.get("content"),
            "importance": node.get("importance", 0.3),
            "status": node.get("status"),        # for goal_steps JS pulsing
            "session_id": node.get("session_id"),
            "timestamp": node.get("timestamp"),
            "color": node.get("color")
        })

    # Sort by importance descending so we keep the most meaningful nodes
    # Always keep goals, goal_steps, reflections (non-interaction tables) first
    priority_tables = {"goals", "goal_steps", "reflections", "projects", "corrections", "preferences"}
    all_nodes.sort(key=lambda n: (
        0 if n["table"] in priority_tables else 1,  # priority tables first
        -(n["importance"] or 0)                      # then by importance desc
    ))

    if len(all_nodes) > MAX_NODES:
        print(f"  [GraphVisualizer] Capping nodes from {len(all_nodes)} to {MAX_NODES} for browser performance.")
        all_nodes = all_nodes[:MAX_NODES]

    kept_ids = {n["id"] for n in all_nodes}

    links = []
    for link in data.get("links", []):
        src = link.get("source")
        tgt = link.get("target")
        # Only include links where both endpoints are in the kept node set
        if src in kept_ids and tgt in kept_ids:
            links.append({
                "source": src,
                "target": tgt,
                "weight": link.get("weight") or 0.5,
                "link_type": link.get("link_type")
            })

    return {"nodes": all_nodes, "links": links}


def export_graph_to_json_full(G: nx.DiGraph) -> dict:
    """
    Exports ALL nodes and links from the graph with no importance cap.
    Used for the 'Deep Memory' toggle in the HTML visualizer.
    Warning: can be very large — only loaded on demand by the browser.
    """
    data = nx.readwrite.json_graph.node_link_data(G, edges="links")
    all_nodes = []
    for node in data.get("nodes", []):
        all_nodes.append({
            "id": node.get("id"),
            "table": node.get("table"),
            "source_id": node.get("source_id"),
            "label": node.get("label"),
            "content": node.get("content"),
            "importance": node.get("importance", 0.3),
            "status": node.get("status"),
            "session_id": node.get("session_id"),
            "timestamp": node.get("timestamp"),
            "color": node.get("color")
        })

    links = []
    all_node_ids = {n["id"] for n in all_nodes}
    for link in data.get("links", []):
        src = link.get("source")
        tgt = link.get("target")
        if src in all_node_ids and tgt in all_node_ids:
            links.append({
                "source": src,
                "target": tgt,
                "weight": link.get("weight") or 0.5,
                "link_type": link.get("link_type")
            })

    return {"nodes": all_nodes, "links": links}


def get_retrieved_memories() -> list[str]:
    """
    Loads the list of retrieved memory node keys (e.g. 'interactions:42') from the last chat turn.
    """
    conn = memory_manager._get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT source_table, source_id FROM retrieved_memories")
        rows = cursor.fetchall()
        return [f"{row['source_table']}:{row['source_id']}" for row in rows]
    except Exception as e:
        # Silently fail if table isn't initialized yet
        return []
    finally:
        conn.close()


def export_graph_to_html(output_path: str = "memory_graph.html") -> str:
    """
    Generates a gorgeous, self-contained interactive D3.js memory graph visualization.
    Embeds both a filtered (fast) dataset and a full (deep) dataset so the user
    can toggle between them live without any server calls.
    Returns the absolute path to the generated HTML file.
    """
    # Build TWO graphs with different interaction thresholds:
    #   G_filtered  — only high-importance interactions (fast, default view)
    #   G_full      — ALL interactions with no threshold (deep memory view)
    print("  [GraphVisualizer] Building filtered graph (fast mode)...")
    G_filtered = build_networkx_graph(interaction_threshold=INTERACTION_IMPORTANCE_THRESHOLD)
    graph_data = export_graph_to_json(G_filtered)          # capped at MAX_NODES

    print("  [GraphVisualizer] Building full graph (deep mode — all memories)...")
    G_full = build_networkx_graph(interaction_threshold=0.0)
    full_graph_data = export_graph_to_json_full(G_full)    # no cap

    retrieved_keys = get_retrieved_memories()

    filtered_count = len(graph_data["nodes"])
    full_count = len(full_graph_data["nodes"])
    

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PANDA — Cognitive Memory Graph</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Space+Mono&display=swap" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
    <style>
        :root {{
            --panel-bg: rgba(4, 8, 20, 0.82);
            --border-color: rgba(99, 102, 241, 0.18);
            --text-primary: #E2E8F0;
            --text-secondary: #94A3B8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background: #020510;
            color: var(--text-primary);
            font-family: 'Outfit', sans-serif;
            height: 100vh;
            overflow: hidden;
            display: flex;
        }}

        /* ── Deep space canvas ── */
        #graph-container {{
            flex: 1;
            height: 100%;
            position: relative;
            background:
                radial-gradient(ellipse 80% 60% at 50% 40%, rgba(30,15,80,0.60) 0%, transparent 70%),
                radial-gradient(ellipse 40% 40% at 20% 70%, rgba(10,40,100,0.35) 0%, transparent 60%),
                radial-gradient(ellipse 50% 50% at 80% 20%, rgba(60,10,80,0.30) 0%, transparent 60%),
                #020510;
        }}

        /* Subtle star-field overlay */
        #graph-container::before {{
            content: '';
            position: absolute;
            inset: 0;
            background-image:
                radial-gradient(1px 1px at 10% 15%, rgba(255,255,255,0.5) 0%, transparent 100%),
                radial-gradient(1px 1px at 30% 80%, rgba(255,255,255,0.35) 0%, transparent 100%),
                radial-gradient(1px 1px at 55% 25%, rgba(255,255,255,0.4) 0%, transparent 100%),
                radial-gradient(1px 1px at 75% 60%, rgba(255,255,255,0.3) 0%, transparent 100%),
                radial-gradient(1px 1px at 90% 10%, rgba(255,255,255,0.45) 0%, transparent 100%),
                radial-gradient(1px 1px at 45% 90%, rgba(255,255,255,0.3) 0%, transparent 100%),
                radial-gradient(1.5px 1.5px at 65% 45%, rgba(200,180,255,0.35) 0%, transparent 100%),
                radial-gradient(1px 1px at 85% 85%, rgba(255,255,255,0.3) 0%, transparent 100%);
            pointer-events: none;
            z-index: 0;
        }}

        /* ── Glassmorphism sidebar ── */
        #control-panel {{
            width: 390px;
            height: 100%;
            background: var(--panel-bg);
            backdrop-filter: blur(20px);
            border-left: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            padding: 24px 20px;
            z-index: 10;
            box-shadow: -12px 0 40px rgba(0,0,0,0.7);
            overflow-y: auto;
        }}

        h1 {{
            font-weight: 800;
            font-size: 22px;
            background: linear-gradient(135deg, #818CF8, #C084FC, #F472B6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 4px;
            letter-spacing: -0.5px;
        }}
        .subtitle {{
            color: var(--text-secondary);
            font-size: 12px;
            margin-bottom: 18px;
            font-family: 'Space Mono', monospace;
        }}

        /* Search */
        .search-input {{
            width: 100%;
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--border-color);
            padding: 10px 14px;
            border-radius: 8px;
            color: var(--text-primary);
            font-family: 'Outfit', sans-serif;
            font-size: 14px;
            outline: none;
            transition: all 0.3s;
            margin-bottom: 16px;
        }}
        .search-input:focus {{
            border-color: #818CF8;
            box-shadow: 0 0 14px rgba(129,140,248,0.3);
        }}

        /* Toggle button */
        .memory-toggle-btn {{
            width: 100%;
            padding: 11px 14px;
            border-radius: 8px;
            border: 1px solid rgba(99,102,241,0.35);
            background: rgba(99,102,241,0.10);
            color: #A5B4FC;
            font-family: 'Outfit', sans-serif;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            margin-bottom: 6px;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .memory-toggle-btn:hover {{
            background: rgba(99,102,241,0.20);
            border-color: rgba(99,102,241,0.65);
            box-shadow: 0 0 18px rgba(99,102,241,0.28);
        }}
        .memory-toggle-btn.deep-active {{
            background: rgba(239,68,68,0.12);
            border-color: rgba(239,68,68,0.45);
            color: #FCA5A5;
        }}
        .toggle-badge {{
            background: rgba(255,255,255,0.08);
            padding: 2px 8px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 800;
        }}
        .deep-warning {{
            display: none;
            font-size: 11px;
            color: rgba(251,191,36,0.9);
            font-weight: 600;
            margin-bottom: 10px;
            padding-left: 2px;
            text-shadow: 0 0 5px rgba(251,191,36,0.4);
        }}
        .deep-warning.visible {{ display: block; }}
        .node-count-label {{
            font-family: 'Space Mono', monospace;
            font-size: 10px;
            color: var(--text-secondary);
            margin-bottom: 14px;
            text-align: center;
        }}

        /* Legend */
        .legend {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 18px;
            padding: 12px;
            background: rgba(255,255,255,0.015);
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            font-size: 12px;
            color: var(--text-secondary);
            gap: 7px;
        }}
        .legend-dot {{
            width: 10px; height: 10px;
            border-radius: 50%;
            flex-shrink: 0;
            box-shadow: 0 0 6px currentColor;
        }}


        /* Node details */
        #node-details {{
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 12px;
            border-top: 1px solid var(--border-color);
            padding-top: 18px;
        }}
        .details-title {{
            font-weight: 600;
            font-size: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .details-badge {{
            font-size: 10px;
            text-transform: uppercase;
            padding: 2px 8px;
            border-radius: 9999px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        .details-card {{
            background: rgba(255,255,255,0.025);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            font-size: 13px;
            line-height: 1.55;
        }}
        .details-meta {{
            font-family: 'Space Mono', monospace;
            font-size: 10px;
            color: var(--text-secondary);
            display: flex;
            flex-direction: column;
            gap: 5px;
        }}

        /* Watermark */
        .watermark {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            pointer-events: none;
            opacity: 0.12;
            z-index: 1;
        }}
        .watermark h2 {{
            font-weight: 800;
            font-size: 26px;
            letter-spacing: 3px;
            background: linear-gradient(135deg, #fff, #818CF8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        /* ── SVG elements ── */
        .node-circle {{
            cursor: pointer;
            transition: filter 0.2s;
        }}
        .node-circle:hover {{
            filter: brightness(1.6) drop-shadow(0 0 8px currentColor);
        }}
        .node-circle.retrieved-node {{
            animation: node-glow-pulse 1.8s infinite ease-in-out;
        }}
        @keyframes node-glow-pulse {{
            0%,100% {{ filter: drop-shadow(0 0 6px #FBBF24); }}
            50%      {{ filter: drop-shadow(0 0 18px #FBBF24); }}
        }}
        .node-circle.in-progress-step {{
            animation: step-pulse 1.4s infinite ease-in-out;
        }}
        @keyframes step-pulse {{
            0%,100% {{ filter: drop-shadow(0 0 4px #06B6D4); }}
            50%      {{ filter: drop-shadow(0 0 12px #06B6D4); }}
        }}

        .text-label {{
            font-family: 'Outfit', sans-serif;
            font-size: 9px;
            fill: #9CA3AF;
            pointer-events: none;
        }}
    </style>
</head>
<body>

    <div id="graph-container">
        <div class="watermark"><h2>PANDA NEURAL MEMORY</h2></div>
    </div>

    <div id="control-panel">
        <h1>P.A.N.D.A.</h1>
        <div class="subtitle">NEURAL MEMORY GRAPH · MARK VI</div>

        <input type="text" class="search-input" id="search-box" placeholder="🔍  Search memory nodes...">

        <button id="memory-toggle-btn" class="memory-toggle-btn" onclick="toggleDeepMemory()">
            <span>🧠 Load Deep Memory</span>
            <span class="toggle-badge" id="toggle-badge">{full_count} nodes</span>
        </button>
        <div id="deep-warning" class="deep-warning">⚡ All {full_count} memory neurons rendered</div>
        <div id="node-count-label" class="node-count-label">
            Showing <strong id="node-count">{filtered_count}</strong> active memory neurons
        </div>

        <!-- Node type legend -->
        <div class="legend">
            <div class="legend-item">
                <span class="legend-dot" style="background:{COLOR_MAP['goals']};color:{COLOR_MAP['goals']};"></span>Goals
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background:{COLOR_MAP['goal_steps']};color:{COLOR_MAP['goal_steps']};"></span>Goal Steps
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background:{COLOR_MAP['projects']};color:{COLOR_MAP['projects']};"></span>Projects
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background:{COLOR_MAP['preferences']};color:{COLOR_MAP['preferences']};"></span>Preferences
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background:{COLOR_MAP['corrections']};color:{COLOR_MAP['corrections']};"></span>Corrections
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background:{COLOR_MAP['reflections']};color:{COLOR_MAP['reflections']};"></span>Reflections
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background:{COLOR_MAP['interactions']};color:{COLOR_MAP['interactions']};"></span>Interactions
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background:#FBBF24;color:#FBBF24;box-shadow:0 0 8px #FBBF24;"></span>Retrieved
            </div>
        </div>


        <div id="node-details">
            <div style="color:var(--text-secondary);text-align:center;margin-top:30px;font-size:13px;line-height:1.6;">
                🧠 Click any neuron<br>to inspect its memory.
            </div>
        </div>
    </div>

    <script>
        const filteredData    = {json.dumps(graph_data)};
        const fullData        = {json.dumps(full_graph_data)};
        const retrievedNodeIds = {json.dumps(retrieved_keys)};

        let currentData = filteredData;
        let isDeepMode  = false;

        const container = document.getElementById('graph-container');
        const width  = container.clientWidth;
        const height = container.clientHeight;

        // ── SVG scaffold ────────────────────────────────────────────────────
        const svg = d3.select("#graph-container")
            .append("svg")
            .attr("width",  "100%")
            .attr("height", "100%")
            .call(d3.zoom().scaleExtent([0.05, 4]).on("zoom", e => g.attr("transform", e.transform)));

        const g = svg.append("g");

        // ── Glow filter definitions ──────────────────────────────────────────
        const defs = svg.append("defs");

        // Generic node glow (per color) — we'll create one per node type
        const nodeColors = {{
            "goals":        "#10B981",
            "goal_steps":   "#06B6D4",
            "projects":     "#3B82F6",
            "preferences":  "#F59E0B",
            "corrections":  "#EF4444",
            "interactions": "#8B5CF6",
            "reflections":  "#EC4899",
        }};
        Object.entries(nodeColors).forEach(([table, color]) => {{
            const filter = defs.append("filter")
                .attr("id", `glow-${{table}}`)
                .attr("x", "-50%").attr("y", "-50%")
                .attr("width", "200%").attr("height", "200%");
            filter.append("feGaussianBlur")
                .attr("stdDeviation", "4")
                .attr("result", "blur");
            const feMerge = filter.append("feMerge");
            feMerge.append("feMergeNode").attr("in", "blur");
            feMerge.append("feMergeNode").attr("in", "SourceGraphic");
        }});

        // Strong glow for retrieved nodes
        const retFilter = defs.append("filter").attr("id", "glow-retrieved")
            .attr("x","-80%").attr("y","-80%").attr("width","260%").attr("height","260%");
        retFilter.append("feGaussianBlur").attr("stdDeviation","8").attr("result","blur");
        const retMerge = retFilter.append("feMerge");
        retMerge.append("feMergeNode").attr("in","blur");
        retMerge.append("feMergeNode").attr("in","SourceGraphic");

        // Arrow markers per link type
        const arrowTypes = [
            {{ id: "arrow-bright", color: "rgba(255,255,255,0.5)" }},
            {{ id: "arrow-dim",    color: "rgba(255,255,255,0.15)" }},
        ];
        arrowTypes.forEach(a => {{
            defs.append("marker")
                .attr("id", a.id)
                .attr("viewBox", "0 -5 10 10")
                .attr("refX", 22).attr("refY", 0)
                .attr("markerWidth", 5).attr("markerHeight", 5)
                .attr("orient", "auto")
                .append("path").attr("d","M0,-5L10,0L0,5").attr("fill", a.color);
        }});

        // ── Rendering engine ─────────────────────────────────────────────────
        let simulation, linkSel, nodeSel, particleLayer;

        // All synaptic lines use a single uniform dim-purple colour.
        // Gold is reserved for actively retrieved memory threads only.
        const SYNAPSE_COLOR = "rgba(139,92,246,0.28)";
        const RETRIEVED_COLOR = "#F59E0B";

        function getLinkWidth(d) {{
            const lt = d.link_type || "";
            if (lt === "plan_step" || lt === "depends_on") return 1.8;
            return 0.8;
        }}

        function getNodeRadius(d) {{
            if (d.table === "goal_steps") return 5;
            return Math.max(6, ((d.importance || 0.3) * 9) + 6);
        }}

        function renderGraph(dataset) {{
            if (simulation) simulation.stop();
            g.selectAll("*").remove();

            // Particle layer (rendered behind nodes)
            particleLayer = g.append("g").attr("class", "particle-layer");

            // ── Force simulation ─────────────────────────────────────────────
            simulation = d3.forceSimulation(dataset.nodes)
                .force("link", d3.forceLink(dataset.links)
                    .id(d => d.id)
                    .distance(d => {{
                        const lt = d.link_type || "";
                        if (lt === "plan_step" || lt === "depends_on") return 60;
                        if (lt === "temporal" || lt === "session_synapse") return 90;
                        return 130;
                    }})
                    .strength(d => {{
                        const lt = d.link_type || "";
                        if (lt === "plan_step" || lt === "depends_on") return 0.9;
                        if (lt === "temporal") return 0.5;
                        if (lt === "session_synapse") return 0.4;
                        return 0.25;
                    }})
                )
                .force("charge", d3.forceManyBody().strength(d => {{
                    if (d.table === "interactions") return -120;
                    return -200;
                }}))
                .force("center", d3.forceCenter(width / 2, height / 2).strength(0.06))
                .force("collision", d3.forceCollide().radius(d => getNodeRadius(d) + 8))
                .alphaDecay(0.015);

            // ── Links — uniform dim synapse colour, gold for retrieved ────────
            linkSel = g.append("g").attr("class", "links-layer")
                .selectAll("line")
                .data(dataset.links)
                .enter().append("line")
                .attr("stroke", d => {{
                    const srcId = typeof d.source === "object" ? d.source.id : d.source;
                    const tgtId = typeof d.target === "object" ? d.target.id : d.target;
                    return (retrievedNodeIds.includes(srcId) || retrievedNodeIds.includes(tgtId))
                        ? RETRIEVED_COLOR : SYNAPSE_COLOR;
                }})
                .attr("stroke-width", d => {{
                    const srcId = typeof d.source === "object" ? d.source.id : d.source;
                    const tgtId = typeof d.target === "object" ? d.target.id : d.target;
                    return (retrievedNodeIds.includes(srcId) || retrievedNodeIds.includes(tgtId)) ? 2.5 : getLinkWidth(d);
                }})
                .attr("stroke-opacity", 0.55)
                .attr("marker-end", "url(#arrow-dim)");

            // ── Nodes ────────────────────────────────────────────────────────
            nodeSel = g.append("g").attr("class", "nodes-layer")
                .selectAll("g")
                .data(dataset.nodes)
                .enter().append("g")
                .call(d3.drag()
                    .on("start", (e,d) => {{ if(!e.active) simulation.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; }})
                    .on("drag",  (e,d) => {{ d.fx=e.x; d.fy=e.y; }})
                    .on("end",   (e,d) => {{ if(!e.active) simulation.alphaTarget(0); d.fx=null; d.fy=null; }})
                );

            // Outer glow ring
            nodeSel.append("circle")
                .attr("r", d => getNodeRadius(d) + 4)
                .attr("fill", "none")
                .attr("stroke", d => d.color)
                .attr("stroke-width", 0.5)
                .attr("stroke-opacity", 0.25)
                .style("filter", d => `url(#glow-${{d.table}})`);

            // Main node circle
            nodeSel.append("circle")
                .attr("class", d => {{
                    let cls = "node-circle";
                    if (retrievedNodeIds.includes(d.id)) cls += " retrieved-node";
                    if (d.table === "goal_steps" && d.status === "in_progress") cls += " in-progress-step";
                    return cls;
                }})
                .attr("r", d => getNodeRadius(d))
                .attr("fill", d => d.color)
                .attr("stroke", d => retrievedNodeIds.includes(d.id) ? "#FBBF24" : "rgba(0,0,0,0.35)")
                .attr("stroke-width", d => retrievedNodeIds.includes(d.id) ? 2.5 : 1.2)
                .style("filter", d => retrievedNodeIds.includes(d.id) ? "url(#glow-retrieved)" : `url(#glow-${{d.table}})`)
                .style("opacity", d => {{
                    if (d.table === "goal_steps") {{
                        if (d.status === "done") return 1.0;
                        if (d.status === "in_progress") return 0.9;
                        return 0.4;
                    }}
                    return 1.0;
                }})
                .on("click", (e,d) => showDetails(d));

            // Text labels — only short abbr + id, no conversation text
            nodeSel.append("text")
                .attr("class", "text-label")
                .attr("dx", d => getNodeRadius(d) + 3)
                .attr("dy", "0.35em")
                .text(d => {{
                    const abbr = {{"interactions":"int","reflections":"ref","goals":"goal",
                                   "goal_steps":"step","projects":"proj","preferences":"pref",
                                   "corrections":"corr"}}[d.table] || d.table.slice(0,3);
                    return abbr + "·" + d.source_id;
                }});

            simulation.on("tick", () => {{
                linkSel
                    .attr("x1", d => d.source.x)
                    .attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x)
                    .attr("y2", d => d.target.y);
                nodeSel.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
            }});
        }}

        // Initial render
        renderGraph(filteredData);

        // ── Deep Memory Toggle ───────────────────────────────────────────────
        function toggleDeepMemory() {{
            isDeepMode = !isDeepMode;
            const btn     = document.getElementById('memory-toggle-btn');
            const badge   = document.getElementById('toggle-badge');
            const warning = document.getElementById('deep-warning');
            const countEl = document.getElementById('node-count');

            if (isDeepMode) {{
                btn.classList.add('deep-active');
                btn.querySelector('span:first-child').textContent = '🧠 Back to Active Memory';
                badge.textContent   = '{filtered_count} nodes';
                warning.classList.add('visible');
                countEl.innerHTML   = '<strong>{full_count}</strong>';
                renderGraph(fullData);
            }} else {{
                btn.classList.remove('deep-active');
                btn.querySelector('span:first-child').textContent = '🧠 Load Deep Memory';
                badge.textContent   = '{full_count} nodes';
                warning.classList.remove('visible');
                countEl.innerHTML   = '<strong>{filtered_count}</strong>';
                renderGraph(filteredData);
            }}
        }}

        // ── Node details sidebar ──────────────────────────────────────────────
        function showDetails(d) {{
            const detailsDiv = document.getElementById("node-details");
            const formattedContent = (d.content || "").replace(/\\n/g, '<br>');

            detailsDiv.innerHTML = `
                <div class="details-title" style="color:${{d.color}}">
                    <span>${{d.label.split(':')[0]}}</span>
                    <span class="details-badge" style="background:${{d.color}};color:#000;">ID ${{d.source_id}}</span>
                </div>
                <div class="details-card">${{formattedContent || '<em style="color:#64748B">No content stored</em>'}}</div>
                <div class="details-card details-meta">
                    <div><strong>Table:</strong> ${{d.table}}</div>
                    <div><strong>Session:</strong> <span style="color:#818CF8">${{d.session_id}}</span></div>
                    <div><strong>Importance:</strong> <span style="color:#10B981">${{(d.importance ?? 0).toFixed(2)}}</span></div>
                    <div><strong>Timestamp:</strong> ${{d.timestamp || '—'}}</div>
                </div>
                <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-top:6px;">
                    ⚡ Synaptic Connections:
                </div>
                <div id="connections-list" style="display:flex;flex-direction:column;gap:6px;max-height:200px;overflow-y:auto;"></div>
            `;

            const connList  = document.getElementById("connections-list");
            let connCount   = 0;

            // Reset link highlights
            linkSel
                .attr("stroke", dd => {{
                    const srcId = typeof dd.source === "object" ? dd.source.id : dd.source;
                    const tgtId = typeof dd.target === "object" ? dd.target.id : dd.target;
                    return (retrievedNodeIds.includes(srcId) || retrievedNodeIds.includes(tgtId))
                        ? RETRIEVED_COLOR : SYNAPSE_COLOR;
                }})
                .attr("stroke-opacity", 0.55);

            linkSel.each(function(l) {{
                const isConn = l.source.id === d.id || l.target.id === d.id;
                if (isConn) {{
                    d3.select(this).attr("stroke", d.color).attr("stroke-opacity", 0.95).attr("stroke-width", 2.5);
                    const other     = l.source.id === d.id ? l.target : l.source;
                    const direction = l.source.id === d.id ? "→" : "←";
                    const item = document.createElement("div");
                    item.style.cssText = `background:rgba(255,255,255,0.02);border:1px solid ${{other.color}};padding:7px 10px;border-radius:6px;font-size:11px;cursor:pointer;`;
                    item.innerHTML = `
                        <span style="color:${{d.color}};font-weight:700;">${{direction}}</span>
                        <span style="color:${{other.color}};font-weight:600;"> ${{other.label.split(':')[0]}}:${{other.source_id}}</span>
                        <span style="color:#64748B;"> [${{l.link_type || 'link'}}] w:${{(l.weight??0).toFixed(2)}}</span>
                    `;
                    item.onclick = () => showDetails(other);
                    connList.appendChild(item);
                    connCount++;
                }}
            }});

            if (connCount === 0) {{
                connList.innerHTML = `<div style="font-size:11px;color:#64748B;font-style:italic;">No direct synaptic connections.</div>`;
            }}
        }}

        // ── Search ───────────────────────────────────────────────────────────
        document.getElementById("search-box").addEventListener("input", function(e) {{
            const query = e.target.value.toLowerCase().trim();
            if (!query) {{
                nodeSel.selectAll("circle").style("opacity", null);
                nodeSel.selectAll("text").style("opacity", null);
                linkSel.style("opacity", null);
                return;
            }}
            nodeSel.each(function(d) {{
                const match = (d.content||"").toLowerCase().includes(query) ||
                              (d.label||"").toLowerCase().includes(query);
                d3.select(this).selectAll("circle").style("opacity", match ? 1 : 0.08);
                d3.select(this).selectAll("text").style("opacity", match ? 1 : 0.05);
            }});
            linkSel.style("opacity", 0.04);
        }});

        // ── Neural signal particle system ─────────────────────────────────────
        // Particles travel along synapses — gold for retrieved threads, soft purple otherwise.
        function spawnParticles() {{
            if (!linkSel) return;
            linkSel.each(function(l) {{
                const src = l.source, tgt = l.target;
                if (!src || !tgt || src.x === undefined) return;

                const isRetrieved = retrievedNodeIds.includes(src.id) || retrievedNodeIds.includes(tgt.id);
                const prob = isRetrieved ? 0.28 : 0.006;
                if (Math.random() > prob) return;

                const color = isRetrieved ? "#FBBF24" : "rgba(167,130,255,0.85)";
                const r     = isRetrieved ? 3.2 : 1.4;
                const dur   = isRetrieved ? 950  : 2800;

                particleLayer.append("circle")
                    .attr("r", r)
                    .attr("fill", color)
                    .attr("cx", src.x).attr("cy", src.y)
                    .attr("opacity", 0.85)
                    .style("filter", isRetrieved ? "drop-shadow(0 0 5px #FBBF24)" : "none")
                    .transition()
                    .duration(dur)
                    .ease(d3.easeLinear)
                    .attr("cx", tgt.x).attr("cy", tgt.y)
                    .attr("opacity", 0)
                    .remove();
            }});
        }}

        d3.interval(spawnParticles, 180);

    </script>
</body>
</html>"""

    abs_output_path = os.path.abspath(output_path)
    with open(abs_output_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    print(f"  [GraphVisualizer] Exported interactive D3 memory graph to: {abs_output_path}")
    return abs_output_path


if __name__ == "__main__":
    print("\n  PANDA Graph Visualizer -- Standalone Export...\n")
    # Set DB Path reference for testing if needed
    html_path = export_graph_to_html("memory_graph.html")
    print(f"  Done! View the graph in your browser: file:///{html_path.replace(os.sep, '/')}\n")
