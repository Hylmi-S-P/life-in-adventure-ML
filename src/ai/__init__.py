"""AI decision engine and RL simulation environment module."""

from src.ai.decision_engine import AIDecisionEngine
from src.ai.policy import CombatStatCalculator, HeuristicPolicy
from src.ai.simulator import LifeInAdventureSimulator
try:
    from src.ai.env import LifeInAdventureEnv
except ImportError:
    LifeInAdventureEnv = None
try:
    from src.ai.curiosity_env import ParallelCuriosityEnv, make_parallel_curiosity_env
    ParallelAdventureEnv = ParallelCuriosityEnv
except ImportError:
    ParallelAdventureEnv = None
    ParallelCuriosityEnv = None
    make_parallel_curiosity_env = None
try:
    from src.ai.rl_trainer import RLTrainer
except ImportError:
    RLTrainer = None
try:
    from src.ai.ppo_trainer import ActorCritic
except ImportError:
    ActorCritic = None

__all__ = [
    "AIDecisionEngine",
    "CombatStatCalculator",
    "HeuristicPolicy",
    "LifeInAdventureSimulator",
    "LifeInAdventureEnv",
    "ParallelAdventureEnv",
    "ParallelCuriosityEnv",
    "make_parallel_curiosity_env",
    "RLTrainer",
    "ActorCritic",
]
