"""
vector_env.py - Parallel Vectorized Environment for Life in Adventure RL Training.
Allows running N (e.g., 5, 10, 20, 50, 100) adventure simulations simultaneously
in parallel memory for ultra-fast policy learning.
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import loguru

from src.rag.knowledge_base import KnowledgeBase
from src.ai.simulator import LifeInAdventureSimulator
from src.ai.env import LifeInAdventureEnv

logger = loguru.logger


class ParallelAdventureEnv:
    """
    Vectorized environment that runs `num_envs` independent LifeInAdventureEnv instances
    simultaneously using a shared KnowledgeBase instance to conserve RAM.
    """

    def __init__(self, num_envs: int = 10, knowledge_base: Optional[KnowledgeBase] = None):
        self.num_envs = num_envs
        self.kb = knowledge_base or KnowledgeBase()
        
        logger.info(f"Initializing {num_envs} parallel simulation environments...")
        self.envs: List[LifeInAdventureEnv] = []
        for _ in range(num_envs):
            sim = LifeInAdventureSimulator(knowledge_base=self.kb)
            env = LifeInAdventureEnv(simulator=sim)
            self.envs.append(env)
            
        self.observation_space_shape = (num_envs, 20)
        self.action_space_n = 5

    def reset(self, seeds: Optional[List[int]] = None) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """Reset all N parallel simulation environments simultaneously."""
        obs_list = []
        info_list = []
        for i, env in enumerate(self.envs):
            seed = seeds[i] if seeds and i < len(seeds) else None
            obs, info = env.reset(seed=seed)
            obs_list.append(obs)
            info_list.append(info)
            
        return np.array(obs_list, dtype=np.float32), info_list

    def step(self, actions: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[Dict[str, Any]]]:
        """
        Execute one step across all N parallel environments simultaneously.
        Automatically resets any environment that terminates or truncates.
        """
        if len(actions) != self.num_envs:
            raise ValueError(f"Expected {self.num_envs} actions, got {len(actions)}")

        obs_list = []
        rewards = np.zeros(self.num_envs, dtype=np.float32)
        terminations = np.zeros(self.num_envs, dtype=bool)
        truncations = np.zeros(self.num_envs, dtype=bool)
        infos = []

        for i, env in enumerate(self.envs):
            act = int(actions[i])
            obs, r, term, trunc, info = env.step(act)
            rewards[i] = r
            terminations[i] = term
            truncations[i] = trunc
            
            # Auto-reset if episode finished
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
            infos
        )

    def close(self):
        """Close all parallel environments."""
        for env in self.envs:
            env.close()
