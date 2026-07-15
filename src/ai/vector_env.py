"""
vector_env.py - Deprecated parallel env.

Use stable-baselines3 DummyVecEnv via:
  from src.ai.curiosity_env import make_parallel_curiosity_env
  from src.ai.rl_trainer import RLTrainer

This module re-exports ParallelCuriosityEnv for backward compatibility.
"""

from src.ai.curiosity_env import ParallelCuriosityEnv

# Alias kept so `from src.ai.vector_env import ParallelAdventureEnv` still works
ParallelAdventureEnv = ParallelCuriosityEnv

__all__ = ["ParallelAdventureEnv", "ParallelCuriosityEnv"]
