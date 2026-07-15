"""
ppo_trainer.py - ActorCritic network for live PPO inference (legacy checkpoint).

Training moved to src/ai/rl_trainer.py (Stable-Baselines3).
This module keeps the ActorCritic architecture so existing
`data/models/ppo_curiosity_latest.pt` checkpoints remain loadable for
AIDecisionEngine low-confidence fallback.

ponytail: custom PPO training loop removed; retrain with:
  python -m src.ai.rl_trainer --timesteps 100000
"""

from typing import Optional, Tuple

import torch
import torch.nn as nn
from torch.distributions.categorical import Categorical


class ActorCritic(nn.Module):
    """
    PyTorch Actor-Critic matching the architecture used for ppo_curiosity_latest.pt.
    Input: 20-dim state. Output: Discrete(5) logits + value.
    """

    def __init__(self, obs_dim: int = 20, action_dim: int = 5, hidden_dim: int = 128):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
        )
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Linear(64, action_dim),
        )
        self.critic = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, obs: torch.Tensor) -> Tuple[Categorical, torch.Tensor]:
        features = self.backbone(obs)
        logits = self.actor(features)
        value = self.critic(features)
        return Categorical(logits=logits), value.squeeze(-1)

    def get_action_and_value(
        self, obs: torch.Tensor, action: Optional[torch.Tensor] = None
    ):
        dist, value = self.forward(obs)
        if action is None:
            action = dist.sample()
        return action, dist.log_prob(action), dist.entropy(), value


# Backward-compat alias — training is in rl_trainer.RLTrainer
class PPOCuriosityTrainer:  # pragma: no cover
    """Deprecated. Use src.ai.rl_trainer.RLTrainer instead."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "PPOCuriosityTrainer removed. Use: from src.ai.rl_trainer import RLTrainer"
        )
