"""
session_logger.py - Session Event Logger for Life in Adventure.
Saves screenshots and logs event RAG context & recommendations to a SQLite database.
Allows recording user evaluations (success/failure) for training purposes.
"""

import os
import sqlite3
import datetime
import threading
from typing import Dict, List, Any, Optional
import loguru
from PIL import Image

logger = loguru.logger


class SessionLogger:
    """Manages active session logging, screenshots, and evaluation feedback database."""

    def __init__(self, base_dir: str = "data/session_history"):
        self.base_dir = base_dir
        self.db_path = os.path.join(self.base_dir, "feedback.sqlite")
        self.screenshots_dir = os.path.join(self.base_dir, "screenshots")
        
        # Ensure directories exist
        os.makedirs(self.screenshots_dir, exist_ok=True)
        
        self.conn = None
        self._init_db()
        
        # Buffer to store log entries captured during the current active session
        self.current_session_logs: List[Dict[str, Any]] = []

    def _init_db(self):
        """Initialize SQLite database schema."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._db_lock = threading.Lock()  # prevent concurrent writes
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedback_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    event_key TEXT,
                    ocr_text TEXT,
                    choice_recommended TEXT,
                    choice_index INTEGER,
                    screenshot_path TEXT,
                    status TEXT,
                    comments TEXT
                )
            """)
            self.conn.commit()
            logger.info(f"Session Logger database initialized at {self.db_path}")
        except Exception as e:
            logger.exception(f"Failed to initialize feedback database: {e}")

    def log_event(
        self,
        event_key: str,
        ocr_text: str,
        choice_recommended: str,
        choice_index: int,
        screenshot_image: Optional[Image.Image] = None
    ) -> Optional[int]:
        """
        Record a decision event. Saves screenshot image and inserts a pending log entry.
        """
        if not self.conn:
            logger.warning("SessionLogger: database not initialized, skipping log_event.")
            return None

        try:
            with self._db_lock:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                screenshot_path = ""
                
                # Save screenshot if provided
                if screenshot_image:
                    # Sanitize event_key for file name safety
                    safe_key = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in event_key])
                    filename = f"{timestamp}_{safe_key}.png"
                    full_path = os.path.join(self.screenshots_dir, filename)
                    screenshot_image.save(full_path, "PNG")
                    screenshot_path = os.path.abspath(full_path)
                    logger.debug(f"Saved screenshot: {screenshot_path}")
    
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO feedback_logs 
                    (timestamp, event_key, ocr_text, choice_recommended, choice_index, screenshot_path, status, comments)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', '')
                """, (timestamp, event_key, ocr_text, choice_recommended, choice_index, screenshot_path, ))
                self.conn.commit()
                
                log_id = cursor.lastrowid
                
                # Create a dictionary to append to the session buffer
                log_entry = {
                    "id": log_id,
                    "timestamp": timestamp,
                    "event_key": event_key,
                    "ocr_text": ocr_text,
                    "choice_recommended": choice_recommended,
                    "choice_index": choice_index,
                    "screenshot_path": screenshot_path,
                    "status": "pending",
                    "comments": ""
                }
                self.current_session_logs.append(log_entry)
                logger.info(f"Logged event '{event_key}' to session logger (ID: {log_id})")
                return log_id
        except Exception as e:
            logger.exception(f"Failed logging event to database: {e}")
            return None

    def update_feedback(self, log_id: int, status: str, comments: str = "") -> bool:
        """
        Update the status ('success' or 'failure') and comments for a specific log ID.
        """
        if not self.conn:
            logger.warning("SessionLogger: database not initialized, skipping update_feedback.")
            return False

        try:
            with self._db_lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    UPDATE feedback_logs 
                    SET status = ?, comments = ?
                    WHERE id = ?
                """, (status, comments, log_id))
                self.conn.commit()
                
                if cursor.rowcount == 0:
                    logger.warning(f"update_feedback: no row found for log_id={log_id}")
                    return False
                
                # Update the buffered log entry in-memory
                for entry in self.current_session_logs:
                    if entry["id"] == log_id:
                        entry["status"] = status
                        entry["comments"] = comments
                        break
                        
            logger.info(f"Feedback updated for log ID {log_id} -> Status: {status}")
            return True
        except Exception as e:
            logger.exception(f"Failed updating feedback for log ID {log_id}: {e}")
            return False

    def get_pending_logs(self) -> List[Dict[str, Any]]:
        """Get all pending/unrated logs for the current active session."""
        return [entry for entry in self.current_session_logs if entry["status"] == "pending"]

    def clear_session_buffer(self):
        """Clear active session buffer logs."""
        self.current_session_logs.clear()

    def close(self):
        """Close SQLite database connection."""
        if self.conn:
            self.conn.close()
