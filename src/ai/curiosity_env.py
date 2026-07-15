"""
curiosity_env.py - Gymnasium env wrappers with CuriosityTracker
for intrinsic novelty exploration and secret ending discovery.

Parallel training uses stable-baselines3 DummyVecEnv via rl_trainer.RLTrainer.
"""

from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import loguru

from src.ai.env import LifeInAdventureEnv
from src.ai.curiosity_tracker import CuriosityTracker
from src.ai.simulator import LifeInAdventureSimulator

logger = loguru.logger

try:
    from stable_baselines3.common.vec_env import DummyVecEnv
    _SB3_AVAILABLE = True
except ImportError:
    _SB3_AVAILABLE = False
    DummyVecEnv = None


class CuriosityAdventureEnv(LifeInAdventureEnv):
    """
    Single-agent env with intrinsic count-based rewards.
    Tracks choice sequences for rare ending discovery.
    """

    def __init__(
        self,
        simulator: Optional[LifeInAdventureSimulator] = None,
        curiosity_tracker: Optional[CuriosityTracker] = None,
    ):
        super().__init__(simulator=simulator)
        self.curiosity_tracker = curiosity_tracker or CuriosityTracker()
        self.episode_choices: List[Dict[str, Any]] = []
        self.step_counter = 0

    def reset(
        self, *, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        self.episode_choices = []
        self.step_counter = 0
        obs, info = super().reset(seed=seed, options=options)

        if self.curiosity_tracker and self.sim.current_event:
            ev_key = self.sim.current_event.get("event_key", "Unknown")
            self.curiosity_tracker.compute_intrinsic_reward_and_record(
                ev_key,
                self.step_counter,
                self.episode_choices,
                self.sim.player.stats,
            )
        return obs, info

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        self.step_counter += 1

        if self.sim.current_event and "choices" in self.sim.current_event:
            choices = self.sim.current_event["choices"]
            ch_idx = min(int(action), len(choices) - 1) if choices else 0
            ch_text = choices[ch_idx].get("text", f"Choice {ch_idx}") if choices else "Action"
            self.episode_choices.append({
                "step": len(self.episode_choices) + 1,
                "from_event": self.sim.current_event.get("event_key", ""),
                "action_idx": ch_idx,
                "choice_text": ch_text,
            })

        obs, extrinsic_reward, terminated, truncated, info = super().step(action)

        intrinsic_reward = 0.0
        if self.curiosity_tracker and self.sim.current_event:
            ev_key = self.sim.current_event.get("event_key", "Unknown")
            intrinsic_reward = self.curiosity_tracker.compute_intrinsic_reward_and_record(
                ev_key,
                self.step_counter,
                self.episode_choices,
                self.sim.player.stats,
            )

        total_reward = extrinsic_reward + intrinsic_reward
        info["extrinsic_reward"] = extrinsic_reward
        info["intrinsic_reward"] = intrinsic_reward
        info["total_discoveries"] = self.curiosity_tracker.total_discoveries

        return obs, total_reward, terminated, truncated, info


def make_parallel_curiosity_env(
    num_envs: int = 8,
    knowledge_base=None,
    curiosity_tracker: Optional[CuriosityTracker] = None,
):
    """
    Build SB3 DummyVecEnv of CuriosityAdventureEnv instances sharing one tracker.
    Preferred parallelization path (replaces ParallelCuriosityEnv / ParallelAdventureEnv).
    """
    if not _SB3_AVAILABLE:
        raise ImportError("stable-baselines3 required for make_parallel_curiosity_env")

    from src.rag.knowledge_base import KnowledgeBase

    kb = knowledge_base or KnowledgeBase()
    tracker = curiosity_tracker or CuriosityTracker()

    def _factory(i: int):
        def _init():
            sim = LifeInAdventureSimulator(knowledge_base=kb)
            return CuriosityAdventureEnv(simulator=sim, curiosity_tracker=tracker)
        return _init

    return DummyVecEnv([_factory(i) for i in range(num_envs)])


class ParallelCuriosityEnv:
    """
    Backward-compat facade. Prefer make_parallel_curiosity_env() or RLTrainer.

    If SB3 available: wraps DummyVecEnv.
    Else: falls back to sequential list of CuriosityAdventureEnv (no true parallel).
    """

    def __init__(
        self,
        num_envs: int = 100,
        knowledge_base=None,
        curiosity_tracker: Optional[CuriosityTracker] = None,
    ):
        self.num_envs = num_envs
        self.curiosity_tracker = curiosity_tracker or CuriosityTracker()
        self._sb3_vec = None
        self.envs: List[CuriosityAdventureEnv] = []

        if _SB3_AVAILABLE:
            self._sb3_vec = make_parallel_curiosity_env(
                num_envs=num_envs,
                knowledge_base=knowledge_base,
                curiosity_tracker=self.curiosity_tracker,
            )
            logger.info(f"ParallelCuriosityEnv: DummyVecEnv x{num_envs}")
        else:
            from src.rag.knowledge_base import KnowledgeBase
            kb = knowledge_base or KnowledgeBase()
            for _ in range(num_envs):
                sim = LifeInAdventureSimulator(knowledge_base=kb)
                self.envs.append(
                    CuriosityAdventureEnv(simulator=sim, curiosity_tracker=self.curiosity_tracker)
                )
            logger.warning(
                f"ParallelCuriosityEnv: sequential fallback x{num_envs} (install stable-baselines3)"
            )

    def reset(self, seeds: Optional[List[int]] = None):
        if self._sb3_vec is not None:
            obs = self._sb3_vec.reset()
            return obs, [{} for _ in range(self.num_envs)]
        obs_list, info_list = [], []
        for i, env in enumerate(self.envs):
            seed = seeds[i] if seeds and i < len(seeds) else None
            obs, info = env.reset(seed=seed)
            obs_list.append(obs)
            info_list.append(info)
        return np.array(obs_list, dtype=np.float32), info_list

    def step(self, actions: np.ndarray):
        if self._sb3_vec is not None:
            obs, rewards, dones, infos = self._sb3_vec.step(actions)
            # SB3 DummyVecEnv merges terminated/truncated into dones
            terminated = dones
            truncated = np.zeros_like(dones)
            return obs, rewards, terminated, truncated, infos
        # Sequential fallback
        obs_list = []
        rewards = np.zeros(self.num_envs, dtype=np.float32)
        terminations = np.zeros(self.num_envs, dtype=bool)
        truncations = np.zeros(self.num_envs, dtype=bool)
        infos = []
        for i, env in enumerate(self.envs):
            obs, r, term, trunc, info = env.step(int(actions[i]))
            rewards[i] = r
            terminations[i] = term
            truncations[i] = trunc
            if term or trunc:
                info["terminal_obs"] = obs.copy()
                obs, reset_info = env.reset()
                info["reset_info"] = reset_info
            obs_list.append(obs)
            infos.append(info)
        return (
            np.array(obs_list, dtype=np.float32),
            rewards,
            terminations,
            truncations,
            infos,
        )

    def close(self):
        if self._sb3_vec is not None:
            self._sb3_vec.close()
        for env in self.envs:
            env.close()
