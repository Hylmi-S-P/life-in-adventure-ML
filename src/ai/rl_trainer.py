"""
rl_trainer.py - Stable-Baselines3 PPO trainer for Life in Adventure curiosity exploration.

Replaces custom ActorCritic training loop in ppo_trainer.py.
Environment: CuriosityAdventureEnv (Gymnasium-compliant, 20-dim obs, Discrete(5)).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import loguru
import numpy as np

from src.ai.curiosity_env import CuriosityAdventureEnv
from src.ai.curiosity_tracker import CuriosityTracker
from src.ai.simulator import LifeInAdventureSimulator
from src.rag.knowledge_base import KnowledgeBase

logger = loguru.logger

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import CheckpointCallback
    from stable_baselines3.common.vec_env import DummyVecEnv
    _SB3_AVAILABLE = True
except ImportError:
    _SB3_AVAILABLE = False
    PPO = None
    DummyVecEnv = None


def _make_env_fn(kb: KnowledgeBase, tracker: CuriosityTracker, seed: int):
    """Factory for one CuriosityAdventureEnv sharing KB + tracker."""
    def _init():
        sim = LifeInAdventureSimulator(knowledge_base=kb)
        env = CuriosityAdventureEnv(simulator=sim, curiosity_tracker=tracker)
        env.reset(seed=seed)
        return env
    return _init


class RLTrainer:
    """SB3 PPO wrapper for parallel curiosity exploration."""

    def __init__(
        self,
        num_envs: int = 8,
        model_dir: str | Path = "data/models",
        tensorboard_log: str = "logs/tensorboard/",
        learning_rate: float = 3e-4,
        n_steps: int = 128,
        batch_size: int = 64,
        n_epochs: int = 4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_range: float = 0.2,
        ent_coef: float = 0.02,
        vf_coef: float = 0.5,
        knowledge_base: Optional[KnowledgeBase] = None,
        curiosity_tracker: Optional[CuriosityTracker] = None,
    ):
        if not _SB3_AVAILABLE:
            raise ImportError("stable-baselines3 not installed. pip install stable-baselines3")

        self.num_envs = num_envs
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.curiosity_tracker = curiosity_tracker or CuriosityTracker()
        self.kb = knowledge_base or KnowledgeBase()

        env_fns = [
            _make_env_fn(self.kb, self.curiosity_tracker, seed=i)
            for i in range(num_envs)
        ]
        # DummyVecEnv: shared process, low overhead for pure-Python sim
        self.venv = DummyVecEnv(env_fns)

        self.model = PPO(
            "MlpPolicy",
            self.venv,
            learning_rate=learning_rate,
            n_steps=n_steps,
            batch_size=batch_size,
            n_epochs=n_epochs,
            gamma=gamma,
            gae_lambda=gae_lambda,
            clip_range=clip_range,
            ent_coef=ent_coef,
            vf_coef=vf_coef,
            tensorboard_log=tensorboard_log,
            verbose=1,
            device="auto",
        )
        logger.info(
            f"RLTrainer ready | envs={num_envs} | discoveries={self.curiosity_tracker.total_discoveries}"
        )

    def train(self, total_timesteps: int = 100_000) -> None:
        """Run PPO training with periodic checkpoints."""
        ckpt = CheckpointCallback(
            save_freq=max(1, 10_000 // self.num_envs),
            save_path=str(self.model_dir),
            name_prefix="ppo_sb3",
        )
        logger.info(f"Training SB3 PPO for {total_timesteps:,} timesteps...")
        self.model.learn(total_timesteps=total_timesteps, callback=ckpt)
        self.save(self.model_dir / "ppo_sb3_latest")
        logger.info(
            f"Training done. Discoveries: {self.curiosity_tracker.total_discoveries}"
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(str(path))
        logger.info(f"Saved SB3 model -> {path}.zip")

    def load(self, path: str | Path) -> bool:
        path = Path(path)
        zip_path = path if path.suffix == ".zip" else Path(f"{path}.zip")
        if not zip_path.exists() and not path.exists():
            logger.warning(f"No SB3 model at {path}")
            return False
        load_target = str(path if path.exists() else zip_path.with_suffix(""))
        self.model = PPO.load(load_target, env=self.venv)
        logger.info(f"Loaded SB3 model from {load_target}")
        return True

    def predict(self, obs: np.ndarray, deterministic: bool = False) -> int:
        """Single-env action prediction (obs shape (20,))."""
        if obs.ndim == 1:
            obs = obs.reshape(1, -1)
        action, _ = self.model.predict(obs, deterministic=deterministic)
        return int(action[0] if hasattr(action, "__len__") else action)

    def close(self) -> None:
        if self.venv is not None:
            self.venv.close()


def main():
    parser = argparse.ArgumentParser(description="SB3 PPO Curiosity Trainer for LiA")
    parser.add_argument("--envs", type=int, default=8, help="Parallel envs (DummyVecEnv)")
    parser.add_argument("--timesteps", type=int, default=50_000, help="Total training steps")
    parser.add_argument("--load", type=str, default=None, help="Path to existing SB3 model")
    args = parser.parse_args()

    trainer = RLTrainer(num_envs=args.envs)
    if args.load:
        trainer.load(args.load)
    trainer.train(total_timesteps=args.timesteps)
    trainer.close()


if __name__ == "__main__":
    main()
