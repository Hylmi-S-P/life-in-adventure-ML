"""
pathfinder.py - Interactive Pathfinder & Walkthrough Engine for Life in Adventure.
Queries the SQLite discovery graph (data/discovered_paths.db) and RAG knowledge base
to print exact step-by-step walkthroughs to reach any secret ending or story event.
"""

import sys
import sqlite3
import json
import argparse
from typing import List, Dict, Any, Optional
import loguru

# Ensure UTF-8 printing safely on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = loguru.logger


class Pathfinder:
    """Finds optimal routes and prints step-by-step walkthroughs from discovered_paths.db."""

    def __init__(self, db_path: str = "data/discovered_paths.db", kb_path: str = "data/lia_kb.sqlite"):
        self.db_path = db_path
        self.kb_path = kb_path

    def search_paths(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search discovered nodes matching query string or event ID."""
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Match exact or partial event_key
                cursor.execute(
                    "SELECT event_key, choice_path, discovered_at, first_discovered_step "
                    "FROM discovered_nodes WHERE event_key LIKE ? ORDER BY length(choice_path) DESC LIMIT ?",
                    (f"%{query}%", limit)
                )
                rows = cursor.fetchall()
    
                for row in rows:
                    event_key, path_json, disc_at, first_step = row
                    try:
                        choice_path = json.loads(path_json)
                    except Exception:
                        choice_path = []
                    
                    results.append({
                        "event_key": event_key,
                        "choice_path": choice_path,
                        "discovered_at": disc_at or "Unknown",
                        "first_step": first_step or 0
                    })
        except Exception as e:
            logger.error(f"Error querying Pathfinder DB: {e}")
    
        return results

    def format_walkthrough(self, path_info: Dict[str, Any]) -> str:
        """Format a discovered path into a clean, human-readable walkthrough."""
        event_key = path_info["event_key"]
        steps = path_info["choice_path"]
        
        lines = [
            f"[Walkthrough Target]: {event_key}",
            f"[Discovered At]: {path_info['discovered_at']} | [First Step]: {path_info['first_step']}",
            "=" * 60
        ]
        
        if not steps:
            lines.append("No step sequence recorded (Root or direct node).")
            return "\n".join(lines)

        for s in steps:
            step_num = s.get("step", "?")
            from_ev = s.get("from_event", "Unknown")
            choice_idx = s.get("action_idx", 0) + 1  # 1-based display
            choice_text = s.get("choice_text", "N/A")
            lines.append(f"Step {step_num:2d} | At [{from_ev:18s}] -> Click Option #{choice_idx}: \"{choice_text}\"")

        lines.append("=" * 60)
        lines.append(f"[Total Steps to Reach Target]: {len(steps)}")
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="LiA Pathfinder & Walkthrough Tool")
    parser.add_argument("--query", "-q", type=str, default="EventMain", help="Event ID or keyword to find")
    parser.add_argument("--limit", "-l", type=int, default=3, help="Max results to display")
    args = parser.parse_args()

    finder = Pathfinder()
    paths = finder.search_paths(args.query, limit=args.limit)
    
    if not paths:
        print(f"[!] No discovered paths found matching query: '{args.query}'")
        return

    for p in paths:
        print("\n" + finder.format_walkthrough(p))


if __name__ == "__main__":
    main()
