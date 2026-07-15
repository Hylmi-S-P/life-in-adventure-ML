"""
env.py - Gymnasium (OpenAI Gym) Environment for Life in Adventure.
Enables parallel training of Reinforcement Learning agents (e.g. Q-Learning, PPO, DQN)
running 100+ episodes simultaneously on offline RAG KnowledgeBase.
"""

import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import loguru

try:
    import gymnasium as gym
    from gymnasium import spaces
    _GYM_AVAILABLE = True
except ImportError:
    _GYM_AVAILABLE = False
    class spaces:
        Discrete = object
        Box = object

from src.ai.simulator import LifeInAdventureSimulator

logger = loguru.logger


class LifeInAdventureEnv(gym.Env if _GYM_AVAILABLE else object):
    """
    Gymnasium-compatible environment for Life in Adventure RL training.
    Observation space: Numeric vector containing player stats, HP, gold, and current choice DCs.
    Action space: Discrete(5) - choice index (0 to 4).
    """

    metadata = {"render_modes": ["ansi", "human"], "render_fps": 30}

    def __init__(self, simulator: Optional[LifeInAdventureSimulator] = None, max_choices: int = 5):
        super().__init__()
        self.sim = simulator or LifeInAdventureSimulator()
        self.max_choices = max_choices

        if _GYM_AVAILABLE:
            # Action space: choose between option 0, 1, 2, 3, 4
            self.action_space = spaces.Discrete(max_choices)
            
            # Observation space: 
            # 6 stats + 1 hp + 1 sanity + 1 gold + 1 step + 5 choice DCs + 5 choice stat IDs = 20 dims
            self.observation_space = spaces.Box(
                low=-1.0, high=100.0, shape=(20,), dtype=np.float32
            )

    def _get_obs_vector(self, obs_dict: Dict[str, Any]) -> np.ndarray:
        """Encode dictionary observation into a flat numeric NumPy array of shape (20,)."""
        vec = np.zeros(20, dtype=np.float32)
        player = obs_dict.get("player", {})
        stats = player.get("stats", {})

        # 0-5: Normalized player stats
        vec[0] = stats.get("str", 10) / 20.0
        vec[1] = stats.get("dex", 10) / 20.0
        vec[2] = stats.get("int", 10) / 20.0
        vec[3] = stats.get("cha", 10) / 20.0
        vec[4] = stats.get("con", 10) / 20.0
        vec[5] = stats.get("wis", 10) / 20.0

        # 6-8: HP, Sanity, Gold
        vec[6] = player.get("hp", 100) / 100.0
        vec[7] = player.get("sanity", 100) / 100.0
        vec[8] = min(10.0, player.get("gold", 50) / 100.0)
        vec[9] = obs_dict.get("step", 0) / 100.0

        # 10-14: Choice DC required (up to 5 choices)
        # 15-19: Choice Stat ID (up to 5 choices)
        choices = obs_dict.get("event", {}).get("choices", [])
        for i in range(min(self.max_choices, len(choices))):
            req = choices[i].get("required", "")
            dc = 0.0
            stat_id = -1.0
            if req and req != "0":
                tokens = req.split("|")[0].split("_")
                if len(tokens) >= 3:
                    try:
                        stat_id = float(tokens[0])
                        dc = float(tokens[2]) / 20.0
                    except ValueError:
                        pass
            vec[10 + i] = dc
            vec[15 + i] = stat_id

        return vec

    def reset(self, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Reset environment for a new training episode."""
        if _GYM_AVAILABLE and seed is not None:
            super().reset(seed=seed)

        obs_dict = self.sim.reset(seed=seed)
        obs_vec = self._get_obs_vector(obs_dict)
        return obs_vec, {"raw_obs": obs_dict}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """Take an action (choice index) and advance simulation."""
        obs_dict, reward, terminated, truncated, info = self.sim.step(int(action))
        obs_vec = self._get_obs_vector(obs_dict)
        info["raw_obs"] = obs_dict
        return obs_vec, float(reward), bool(terminated), bool(truncated), info

    def render(self) -> Optional[str]:
        """Render current event and choices to text/console."""
        if not self.sim.current_event:
            return "Game Over / No Event"
        ev = self.sim.current_event
        txt = ev.get("clean_text", "")[:120]
        out = f"\n=== [Event: {ev.get('event_key')}] ===\n{txt}\nChoices:\n"
        for idx, ch in enumerate(ev.get("choices", [])):
            out += f"  [{idx}] {ch.get('text', '')} (Check: {ch.get('required', 'None')})\n"
        return out

    def close(self):
        """Close simulator / knowledge base."""
        pass
