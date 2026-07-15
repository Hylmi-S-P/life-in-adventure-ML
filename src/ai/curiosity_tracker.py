"""
curiosity_tracker.py - Novelty/Count-based Intrinsic Reward Tracker and Discovery Graph.
Tracks event visit counts across 100x parallel simulations and records newly discovered
secret paths/endings directly to SQLite (`data/discovered_paths.db`).
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Tuple
import threading
import loguru

logger = loguru.logger


class CuriosityTracker:
    """
    Manages intrinsic rewards based on visitation counts (1.0 / sqrt(count + 1)).
    When a rare or unseen event node is reached, awards high intrinsic novelty bonus
    and logs the exact quest path to SQLite database.
    """

    def __init__(self, db_path: Path = Path("data/discovered_paths.db")):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        
        # Fast in-memory lookup table: event_key -> visit_count
        self.visit_counts: Dict[str, int] = {}
        self.total_discoveries = 0
        
        self._init_db()

    def _init_db(self):
        """Initialize SQLite schema for tracking discovered secret paths."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS discovered_nodes (
                    event_key TEXT PRIMARY KEY,
                    first_discovered_step INTEGER,
                    choice_path TEXT,
                    player_stats TEXT,
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            
            # Load existing discovery counts into memory
            cursor.execute("SELECT event_key FROM discovered_nodes")
            rows = cursor.fetchall()
            for row in rows:
                self.visit_counts[row[0]] = 1
            self.total_discoveries = len(rows)
            
        logger.info(f"CuriosityTracker initialized. Loaded {self.total_discoveries} previously discovered nodes.")

    def compute_intrinsic_reward_and_record(
        self,
        event_key: str,
        step_idx: int,
        choice_path: List[Dict[str, Any]],
        player_stats: Dict[str, int]
    ) -> float:
        """
        Calculate count-based novelty reward and record to DB if first visit.
        """
        if not event_key or event_key == "Unknown":
            return 0.0

        with self.lock:
            count = self.visit_counts.get(event_key, 0)
            self.visit_counts[event_key] = count + 1
            
            # Intrinsic novelty calculation: R_intrinsic = 15.0 / (count + 1)^0.5
            intrinsic_reward = 15.0 / ((count + 1) ** 0.5)

            # First time ever discovered across any parallel run!
            if count == 0:
                self.total_discoveries += 1
                intrinsic_reward += 100.0  # Huge bonus for new discovery
                logger.success(f"🌟 NEW DISCOVERY #{self.total_discoveries}: '{event_key}' (Intrinsic Bonus: +115.0)")
                
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO discovered_nodes 
                            (event_key, first_discovered_step, choice_path, player_stats)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                event_key,
                                step_idx,
                                json.dumps(choice_path, ensure_ascii=False),
                                json.dumps(player_stats, ensure_ascii=False)
                            )
                        )
                        conn.commit()
                except Exception as e:
                    logger.error(f"Failed to save discovery to SQLite: {e}")

            return round(intrinsic_reward, 3)

    def get_stats(self) -> Dict[str, int]:
        """Return discovery metrics."""
        with self.lock:
            return {
                "total_unique_nodes_visited": len(self.visit_counts),
                "total_discoveries": self.total_discoveries
            }
