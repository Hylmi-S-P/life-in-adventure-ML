"""
ppo_trainer.py - Deep Reinforcement Learning (PPO) + Curiosity Novelty Trainer.
Trains an Actor-Critic Neural Network on 100x Parallel Simulator (`ParallelCuriosityEnv`)
to discover optimal stat builds, quest paths, and secret story endings.
"""

import os
import argparse
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import loguru

import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions.categorical import Categorical

from src.ai.curiosity_env import ParallelCuriosityEnv
from src.ai.curiosity_tracker import CuriosityTracker

logger = loguru.logger


class ActorCritic(nn.Module):
    """
    PyTorch Neural Network for PPO Actor-Critic.
    Input: 20-dim state vector (Stats, HP, Sanity, Gold, XP, Event embedding hash).
    Output: Action logits (5 choices) and State Value estimation.
    """

    def __init__(self, obs_dim: int = 20, action_dim: int = 5, hidden_dim: int = 128):
        super().__init__()
        
        # Shared feature extractor
        self.backbone = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU()
        )
        
        # Actor head (Policy logits)
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Linear(64, action_dim)
        )
        
        # Critic head (Value estimation V(s))
        self.critic = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1)
        )

    def forward(self, obs: torch.Tensor) -> Tuple[Categorical, torch.Tensor]:
        features = self.backbone(obs)
        logits = self.actor(features)
        value = self.critic(features)
        dist = Categorical(logits=logits)
        return dist, value.squeeze(-1)

    def get_action_and_value(self, obs: torch.Tensor, action: Optional[torch.Tensor] = None):
        dist, value = self.forward(obs)
        if action is None:
            action = dist.sample()
        return action, dist.log_prob(action), dist.entropy(), value


class PPOCuriosityTrainer:
    """Orchestrates 100x parallel simulation rollouts and PPO optimization."""

    def __init__(
        self,
        num_envs: int = 100,
        obs_dim: int = 20,
        action_dim: int = 5,
        lr: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_coef: float = 0.2,
        ent_coef: float = 0.02,
        vf_coef: float = 0.5,
        model_save_dir: Path = Path("data/models")
    ):
        self.num_envs = num_envs
        self.obs_dim = obs_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_coef = clip_coef
        self.ent_coef = ent_coef
        self.vf_coef = vf_coef
        self.model_save_dir = model_save_dir
        self.model_save_dir.mkdir(parents=True, exist_ok=True)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"PPO Trainer initializing on device: {self.device}")

        self.policy = ActorCritic(obs_dim, action_dim).to(self.device)
        self.optimizer = optim.Adam(self.policy.parameters(), lr=lr, eps=1e-5)
        
        self.curiosity_tracker = CuriosityTracker()
        self.venv = ParallelCuriosityEnv(num_envs=num_envs, curiosity_tracker=self.curiosity_tracker)
        self.start_epoch = 1

    def save_checkpoint(self, epoch: int, filename: str = "ppo_curiosity_latest.pt"):
        """Save PyTorch policy weights and optimizer state."""
        save_path = self.model_save_dir / filename
        torch.save({
            "epoch": epoch,
            "policy_state_dict": self.policy.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "total_discoveries": self.curiosity_tracker.total_discoveries
        }, save_path)
        logger.info(f"Saved PPO Curiosity model checkpoint -> {save_path}")

    def load_checkpoint(self, filename: str = "ppo_curiosity_latest.pt") -> bool:
        """Load PyTorch model if exists."""
        load_path = self.model_save_dir / filename
        if load_path.exists():
            checkpoint = torch.load(load_path, map_location=self.device)
            self.policy.load_state_dict(checkpoint["policy_state_dict"])
            self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
            saved_epoch = checkpoint.get("epoch", 0)
            self.start_epoch = saved_epoch + 1
            logger.info(f"Loaded existing PPO model from {load_path} (Previous Epoch: {saved_epoch}, Resuming at Epoch: {self.start_epoch})")
            return True
        return False

    def train(self, total_epochs: int = 50, rollout_steps: int = 128):
        """Run PPO training loop across 100 parallel environments."""
        logger.info(f"Starting PPO Curiosity Training | Envs: {self.num_envs} | Epochs: {total_epochs} | Rollout steps: {rollout_steps}")
        
        obs_batch, _ = self.venv.reset()
        obs_tensor = torch.tensor(obs_batch, dtype=torch.float32, device=self.device)

        start_time = time.time()
        for epoch in range(self.start_epoch, max(self.start_epoch, total_epochs + 1)):
            # Storage for rollout buffers
            b_obs = torch.zeros((rollout_steps, self.num_envs, self.obs_dim), device=self.device)
            b_actions = torch.zeros((rollout_steps, self.num_envs), dtype=torch.long, device=self.device)
            b_logprobs = torch.zeros((rollout_steps, self.num_envs), device=self.device)
            b_rewards = torch.zeros((rollout_steps, self.num_envs), device=self.device)
            b_dones = torch.zeros((rollout_steps, self.num_envs), device=self.device)
            b_values = torch.zeros((rollout_steps, self.num_envs), device=self.device)

            epoch_extrinsic_sum = 0.0
            epoch_intrinsic_sum = 0.0

            # 1. Collect Rollout
            for step in range(rollout_steps):
                b_obs[step] = obs_tensor
                
                with torch.no_grad():
                    action, logprob, _, value = self.policy.get_action_and_value(obs_tensor)
                    b_values[step] = value
                
                actions_cpu = action.cpu().numpy()
                next_obs, rewards, terminated, truncated, infos = self.venv.step(actions_cpu)
                
                dones = np.logical_or(terminated, truncated)
                b_actions[step] = action
                b_logprobs[step] = logprob
                b_rewards[step] = torch.tensor(rewards, dtype=torch.float32, device=self.device)
                b_dones[step] = torch.tensor(dones, dtype=torch.float32, device=self.device)

                obs_tensor = torch.tensor(next_obs, dtype=torch.float32, device=self.device)
                
                for info in infos:
                    epoch_extrinsic_sum += info.get("extrinsic_reward", 0.0)
                    epoch_intrinsic_sum += info.get("intrinsic_reward", 0.0)

            # 2. Generalized Advantage Estimation (GAE)
            with torch.no_grad():
                _, next_value = self.policy.forward(obs_tensor)
                advantages = torch.zeros_like(b_rewards, device=self.device)
                lastgaelam = 0
                for t in reversed(range(rollout_steps)):
                    if t == rollout_steps - 1:
                        nextnonterminal = 1.0 - b_dones[t]
                        nextvalues = next_value
                    else:
                        nextnonterminal = 1.0 - b_dones[t + 1]
                        nextvalues = b_values[t + 1]
                    delta = b_rewards[t] + self.gamma * nextvalues * nextnonterminal - b_values[t]
                    advantages[t] = lastgaelam = delta + self.gamma * self.gae_lambda * nextnonterminal * lastgaelam
                returns = advantages + b_values

            # 3. Flatten batches for optimization
            b_obs_flat = b_obs.reshape(-1, self.obs_dim)
            b_actions_flat = b_actions.reshape(-1)
            b_logprobs_flat = b_logprobs.reshape(-1)
            b_advantages_flat = advantages.reshape(-1)
            b_returns_flat = returns.reshape(-1)
            b_values_flat = b_values.reshape(-1)

            # 4. PPO Update (4 mini-batch epochs)
            dataset_size = rollout_steps * self.num_envs
            batch_size = dataset_size // 4
            indices = np.arange(dataset_size)
            
            for _ in range(4):
                np.random.shuffle(indices)
                for start_idx in range(0, dataset_size, batch_size):
                    end_idx = start_idx + batch_size
                    mb_idx = indices[start_idx:end_idx]

                    _, newlogprob, entropy, newvalue = self.policy.get_action_and_value(
                        b_obs_flat[mb_idx], b_actions_flat[mb_idx]
                    )
                    logratio = newlogprob - b_logprobs_flat[mb_idx]
                    ratio = logratio.exp()

                    mb_advantages = b_advantages_flat[mb_idx]
                    mb_advantages = (mb_advantages - mb_advantages.mean()) / (mb_advantages.std() + 1e-8)

                    # Clipped policy loss
                    pg_loss1 = -mb_advantages * ratio
                    pg_loss2 = -mb_advantages * torch.clamp(ratio, 1.0 - self.clip_coef, 1.0 + self.clip_coef)
                    pg_loss = torch.max(pg_loss1, pg_loss2).mean()

                    # Value loss
                    v_loss = 0.5 * ((newvalue - b_returns_flat[mb_idx]) ** 2).mean()

                    # Entropy loss (encourages exploration)
                    entropy_loss = entropy.mean()

                    loss = pg_loss - self.ent_coef * entropy_loss + self.vf_coef * v_loss

                    self.optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(self.policy.parameters(), 0.5)
                    self.optimizer.step()

            # Logging metrics
            elapsed = time.time() - start_time
            fps = int((epoch * rollout_steps * self.num_envs) / max(1e-5, elapsed))
            mean_ext = epoch_extrinsic_sum / (rollout_steps * self.num_envs)
            mean_int = epoch_intrinsic_sum / (rollout_steps * self.num_envs)
            stats = self.curiosity_tracker.get_stats()

            logger.info(
                f"Epoch [{epoch:02d}/{total_epochs:02d}] | FPS: {fps} | Mean Reward (Ext/Int): {mean_ext:.2f} / {mean_int:.2f} | "
                f"Discovered Nodes: {stats['total_discoveries']}"
            )

            # Checkpoint every 5 epochs or at the end
            if epoch % 5 == 0 or epoch == total_epochs:
                self.save_checkpoint(epoch)


def main():
    parser = argparse.ArgumentParser(description="PPO Curiosity Trainer for Life in Adventure")
    parser.add_argument("--envs", type=int, default=100, help="Number of parallel environments")
    parser.add_argument("--epochs", type=int, default=10, help="Number of PPO training epochs")
    parser.add_argument("--steps", type=int, default=64, help="Rollout steps per epoch")
    args = parser.parse_args()

    trainer = PPOCuriosityTrainer(num_envs=args.envs)
    trainer.load_checkpoint()
    trainer.train(total_epochs=args.epochs, rollout_steps=args.steps)


if __name__ == "__main__":
    main()
