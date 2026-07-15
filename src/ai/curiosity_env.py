"""
curiosity_env.py - Gymnasium environment wrappers equipped with CuriosityTracker
for Intrinsic Novelty Exploration and Secret Ending Discovery.
"""

from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import loguru

from src.ai.env import LifeInAdventureEnv
from src.ai.vector_env import ParallelAdventureEnv
from src.ai.curiosity_tracker import CuriosityTracker
from src.ai.simulator import LifeInAdventureSimulator

logger = loguru.logger


class CuriosityAdventureEnv(LifeInAdventureEnv):
    """
    Single-agent environment augmented with intrinsic count-based rewards.
    Tracks choice sequences to log complete paths when rare endings are reached.
    """

    def __init__(self, simulator: Optional[LifeInAdventureSimulator] = None, curiosity_tracker: Optional[CuriosityTracker] = None):
        super().__init__(simulator=simulator)
        self.curiosity_tracker = curiosity_tracker or CuriosityTracker()
        self.episode_choices: List[Dict[str, Any]] = []
        self.step_counter = 0

    def reset(self, *, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        self.episode_choices = []
        obs, info = super().reset(seed=seed, options=options)
        
        # Log initial event discovery
        if self.curiosity_tracker and self.sim.current_event:
            ev_key = self.sim.current_event.get("event_key", "Unknown")
            self.curiosity_tracker.compute_intrinsic_reward_and_record(
                ev_key,
                self.step_counter,
                self.episode_choices,
                self.sim.player.stats
            )
        return obs, info

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        self.step_counter += 1
        
        # Record choice taken before step
        if self.sim.current_event and "choices" in self.sim.current_event:
            choices = self.sim.current_event["choices"]
            ch_idx = min(int(action), len(choices) - 1) if choices else 0
            ch_text = choices[ch_idx].get("text", f"Choice {ch_idx}") if choices else "Action"
            self.episode_choices.append({
                "step": len(self.episode_choices) + 1,
                "from_event": self.sim.current_event.get("event_key", ""),
                "action_idx": ch_idx,
                "choice_text": ch_text
            })

        obs, extrinsic_reward, terminated, truncated, info = super().step(action)

        # Compute intrinsic curiosity reward for arriving at new event
        intrinsic_reward = 0.0
        if self.curiosity_tracker and self.sim.current_event:
            ev_key = self.sim.current_event.get("event_key", "Unknown")
            intrinsic_reward = self.curiosity_tracker.compute_intrinsic_reward_and_record(
                ev_key,
                self.step_counter,
                self.episode_choices,
                self.sim.player.stats
            )

        total_reward = extrinsic_reward + intrinsic_reward
        info["extrinsic_reward"] = extrinsic_reward
        info["intrinsic_reward"] = intrinsic_reward
        info["total_discoveries"] = self.curiosity_tracker.total_discoveries

        return obs, total_reward, terminated, truncated, info


class ParallelCuriosityEnv(ParallelAdventureEnv):
    """
    Parallel Vectorized Environment running 100x simultaneous CuriosityAdventureEnvs.
    Shares a single CuriosityTracker across all threads/envs.
    """

    def __init__(self, num_envs: int = 100, knowledge_base: Optional[Any] = None, curiosity_tracker: Optional[CuriosityTracker] = None):
        super().__init__(num_envs=num_envs, knowledge_base=knowledge_base)
        self.curiosity_tracker = curiosity_tracker or CuriosityTracker()
        
        # Re-wrap each env with CuriosityAdventureEnv
        for i in range(num_envs):
            self.envs[i] = CuriosityAdventureEnv(
                simulator=self.envs[i].sim,
                curiosity_tracker=self.curiosity_tracker
            )
