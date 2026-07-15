"""AI decision engine and RL simulation environment module."""

from src.ai.decision_engine import AIDecisionEngine
from src.ai.policy import CombatStatCalculator, HeuristicPolicy
from src.ai.simulator import LifeInAdventureSimulator
try:
    from src.ai.env import LifeInAdventureEnv
except ImportError:
    LifeInAdventureEnv = None
try:
    from src.ai.vector_env import ParallelAdventureEnv
except ImportError:
    ParallelAdventureEnv = None

__all__ = [
    "AIDecisionEngine",
    "CombatStatCalculator",
    "HeuristicPolicy",
    "LifeInAdventureSimulator",
    "LifeInAdventureEnv",
    "ParallelAdventureEnv",
]
