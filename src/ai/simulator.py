"""
simulator.py - Offline Game Simulator for Life in Adventure.
Allows high-speed simulation of game events, stat checks, combat logic, and inventory
for RL agent training without requiring a running Android emulator.
"""

import random
from typing import Dict, List, Any, Optional, Tuple
import loguru

from src.rag.knowledge_base import KnowledgeBase

logger = loguru.logger


class PlayerState:
    """Represents the player's character sheet and inventory during a simulated run."""
    def __init__(self):
        self.stats = {
            "str": 10,
            "dex": 10,
            "int": 10,
            "cha": 10,
            "con": 10,
            "wis": 10
        }
        self.hp = 100
        self.max_hp = 100
        self.sanity = 100
        self.max_sanity = 100
        self.gold = 50
        self.xp = 0
        self.level = 1
        self.inventory: List[str] = ["Short Sword", "Leather Armor"]
        self.alignment = {"good_evil": 0, "law_chaos": 0}
        self.alive = True

    def get_stat_modifier(self, stat_name: str) -> int:
        """Calculate D20 modifier: (stat - 10) // 2."""
        val = self.stats.get(stat_name.lower(), 10)
        return (val - 10) // 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stats": self.stats.copy(),
            "hp": self.hp,
            "max_hp": self.max_hp,
            "sanity": self.sanity,
            "gold": self.gold,
            "xp": self.xp,
            "level": self.level,
            "inventory": self.inventory.copy(),
            "alignment": self.alignment.copy(),
            "alive": self.alive
        }


class LifeInAdventureSimulator:
    """
    Simulates Life in Adventure adventure runs using offline event records from KnowledgeBase.
    Supports stat checks, reward applications, state transitions, and episode rewards.
    """

    def __init__(self, knowledge_base: Optional[KnowledgeBase] = None):
        self.kb = knowledge_base or KnowledgeBase()
        self.player = PlayerState()
        self.current_event: Optional[Dict[str, Any]] = None
        self.turn_step = 0
        self.max_steps = 100
        self.history: List[Dict[str, Any]] = []

    def reset(self, seed: Optional[int] = None, start_event_key: str = "EventMain0_0_0") -> Dict[str, Any]:
        """Reset simulator to the start of a new adventure run."""
        if seed is not None:
            random.seed(seed)

        self.player = PlayerState()
        self.turn_step = 0
        self.history = []

        # Try loading starting event
        start_ev = self.kb.get_event_by_key(start_event_key)
        if not start_ev:
            # Fallback: get random event if specific start key not found
            rows = self.kb.search_events("모험", top_k=1, use_vector=False)
            start_ev = rows[0][0] if rows else None

        self.current_event = start_ev
        return self.get_observation()

    def get_observation(self) -> Dict[str, Any]:
        """Return structured observation for the RL environment or AI engine."""
        return {
            "player": self.player.to_dict(),
            "event": {
                "event_key": self.current_event.get("event_key") if self.current_event else None,
                "clean_text": self.current_event.get("clean_text", "") if self.current_event else "",
                "choices": self.current_event.get("choices", []) if self.current_event else []
            },
            "step": self.turn_step
        }

    def _resolve_next_event_key(self, stem: str, event_id: int) -> Optional[str]:
        """
        Map game nextEvent id to real SQLite event_key (stem_id_idx).
        Prefer exact stem_id_id, else first matching id under source_file.
        """
        candidate = f"{stem}_{event_id}_{event_id}"
        if self.kb and self.kb.get_event_by_key(candidate):
            return candidate
        if not self.kb or not getattr(self.kb, "conn", None):
            return candidate
        try:
            cur = self.kb.conn.cursor()
            cur.execute(
                "SELECT event_key FROM events WHERE source_file = ? AND id = ? LIMIT 1",
                (stem, event_id),
            )
            row = cur.fetchone()
            if row:
                return row["event_key"] if hasattr(row, "keys") else row[0]
        except Exception as e:
            logger.debug(f"next_event resolve failed: {e}")
        return candidate

    def _eval_stat_check(self, req_code: str) -> bool:
        """
        Evaluate a D20 check string like '0_2_12' (STR check DC 12).
        '|' separates OR alternatives — pass if any alternative succeeds.
        """
        if not req_code or req_code == "0":
            return True

        stat_map = {0: "str", 1: "dex", 2: "int", 3: "cha", 4: "con", 5: "wis"}
        parts = [p for p in req_code.split("|") if p.strip()]
        if not parts:
            return True

        any_evaluable = False
        for p in parts:
            tokens = p.split("_")
            if len(tokens) >= 3:
                try:
                    stat_id = int(tokens[0])
                    dc = int(tokens[2])
                    stat_name = stat_map.get(stat_id, "str")
                    mod = self.player.get_stat_modifier(stat_name)
                    roll = random.randint(1, 20)
                    any_evaluable = True
                    if roll + mod >= dc:
                        return True  # OR: any success wins
                except ValueError:
                    continue
        # All evaluable alternatives failed, or nothing evaluable → free pass
        return not any_evaluable

    def _apply_results(self, results: List[Dict[str, Any]]) -> Tuple[float, Optional[str]]:
        """
        Apply consequences from a choice result (HP changes, gold, stat gains, next event).
        Returns (reward_delta, next_event_key).
        """
        reward = 0.0
        next_event_key = None

        for res in results:
            res_type = str(res.get("type", ""))
            val = res.get("value", 0)

            # Parse reward string if present (e.g., '0_2_1|0_4_4' or '6_1_0')
            reward_str = str(res.get("reward", ""))
            if reward_str:
                for part in reward_str.split("|"):
                    tokens = part.split("_")
                    if len(tokens) >= 3:
                        try:
                            r_cat = int(tokens[0])
                            r_sub = int(tokens[1])
                            r_val = int(tokens[2])
                            if r_cat == 0:  # Stat/HP/Sanity changes
                                if r_sub == 0:  # HP
                                    self.player.hp = max(0, min(self.player.max_hp, self.player.hp + r_val))
                                    reward += r_val * 0.1
                                elif r_sub == 1:  # Sanity
                                    self.player.sanity = max(0, min(self.player.max_sanity, self.player.sanity + r_val))
                                    reward += r_val * 0.05
                                else:  # Stat check reward
                                    reward += r_val * 1.5
                            elif r_cat == 1:  # Gold / XP
                                self.player.gold += r_val
                                reward += r_val * 0.02
                        except ValueError:
                            pass

            # Handle nextEvent jumping
            next_ev_val = res.get("nextEvent")
            if next_ev_val is not None:
                if isinstance(next_ev_val, int):
                    if next_ev_val == -3:
                        self.player.alive = False
                        reward -= 15.0
                    elif next_ev_val == -2 or next_ev_val == -1:
                        next_event_key = None  # End of node / map transition
                    else:
                        # Resolve real event_key: stem_id_idx (idx may != id)
                        if self.current_event and self.current_event.get("source_file"):
                            stem = self.current_event["source_file"]
                            next_event_key = self._resolve_next_event_key(stem, next_ev_val)
                elif isinstance(next_ev_val, str):
                    next_event_key = next_ev_val

        # Death by HP only if not already penalized via nextEvent=-3
        if self.player.hp <= 0 and self.player.alive:
            self.player.alive = False
            reward -= 15.0
        elif self.player.hp <= 0:
            self.player.alive = False

        return reward, next_event_key

    def step(self, choice_idx: int) -> Tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        """
        Advance one step by selecting choice_idx from the current event's available choices.
        Returns (observation, reward, terminated, truncated, info).
        """
        self.turn_step += 1
        reward = 0.0
        terminated = False
        truncated = self.turn_step >= self.max_steps

        if not self.current_event or not self.player.alive:
            terminated = True
            return self.get_observation(), 0.0, terminated, truncated, {"reason": "game_over"}

        choices = self.current_event.get("choices", [])
        if not choices:
            # End of branch / episode
            terminated = True
            reward += 10.0  # Completed episode bonus
            return self.get_observation(), reward, terminated, truncated, {"reason": "end_of_story"}

        # Validate choice index
        if choice_idx < 0 or choice_idx >= len(choices):
            choice_idx = 0

        chosen = choices[choice_idx]
        req = chosen.get("required", "")
        passed = self._eval_stat_check(req)

        if passed:
            reward += 1.0
        else:
            reward -= 1.0

        # Apply results from chosen branch
        results = chosen.get("results", [])
        delta_r, next_key = self._apply_results(results)
        reward += delta_r

        # Record history
        self.history.append({
            "step": self.turn_step,
            "event_key": self.current_event.get("event_key"),
            "choice_text": chosen.get("text", ""),
            "passed_check": passed,
            "reward": reward
        })

        # Transition to next event
        if not self.player.alive:
            terminated = True
        elif next_key:
            next_ev = self.kb.get_event_by_key(next_key)
            if next_ev:
                self.current_event = next_ev
            else:
                # If next_key not found in offline DB, sample next step or terminate
                terminated = True
        else:
            # Sample next valid event from offline DB randomly to keep run continuing
            all_keys = list(self.kb.event_records.keys())
            if all_keys:
                random_key = random.choice(all_keys)
                self.current_event = self.kb.get_event_with_choices(random_key)
            else:
                terminated = True

        return self.get_observation(), round(reward, 3), terminated, truncated, {
            "passed_check": passed,
            "choice_text": chosen.get("text", ""),
            "player_alive": self.player.alive
        }
