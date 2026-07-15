"""Configuration loader."""

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional, List

import yaml
import os
# NOTE: The following YAML config sections are consumed at runtime but not
# modeled as dataclasses (parsed as raw dicts where needed):
#   - capture: adaptive_mode, interval_min/max, preprocess_steps, resize_factor
#   - knowledge_base: version, source_apk_version, total_quests/events/choices/epilogues
#   - overlay.hotkeys: dict of key bindings
#   - privacy: gdpr_enabled, consent_modal (referenced in SECURITY_PRIVACY.md)
#   - logging: level, rotation, retention, telemetry
# TODO: Add dedicated dataclasses for these sections when their features are implemented.

@dataclass
class ZCodeConfig:
    """ZCode provider configuration (nested inside ai config)"""
    base_url: str = "https://gateway.olagon.site/anthropic"  # Updated per SPEC.md §8.1 and ARCHITECTURE.md §5
    api_key_env: str = "ZCODE_API_KEY"
    _api_key: Optional[str] = field(default=None, repr=False)

    def __init__(self, base_url: str = "https://gateway.olagon.site/anthropic", api_key_env: str = "ZCODE_API_KEY", api_key: Optional[str] = None, **kwargs):
        self.base_url = base_url
        self.api_key_env = api_key_env
        self._api_key = api_key

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key or os.getenv(self.api_key_env)


@dataclass
class OpenAIConfig:
    """OpenAI provider configuration"""
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    _api_key: Optional[str] = field(default=None, repr=False)

    def __init__(self, base_url: str = "https://api.openai.com/v1", api_key_env: str = "OPENAI_API_KEY", api_key: Optional[str] = None, **kwargs):
        self.base_url = base_url
        self.api_key_env = api_key_env
        self._api_key = api_key

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key or os.getenv(self.api_key_env)


@dataclass
class OllamaConfig:
    """Ollama (local LLM) provider configuration"""
    base_url: str = "http://localhost:11434"
    model: str = "llama3.2"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2", **kwargs):
        self.base_url = base_url
        self.model = model


@dataclass
class EmulatorConfig:
    type: str = "ldplayer"
    capture_interval: float = 3.0
    auto_detect: bool = True
    window_title: str | None = None
    capture_region: tuple[int, int, int, int] | None = None


@dataclass
class OverlayConfig:
    position: str = "right"
    custom_pos: tuple[int, int] | None = None
    width: int = 450
    height: int = 650
    opacity: float = 0.85
    bg_color: str = "#1a1a2e"
    text_color: str = "#e0e0e0"
    accent_color: str = "#00d4ff"
    font_size: int = 11
    theme: str = "dark"
    hotkeys: dict = field(default_factory=lambda: {"toggle": "F9", "refresh_kb": "F10", "quit": "F12", "settings": "F11"})


@dataclass
class AIConfig:
    provider: str = "zcode"
    model: str = "claude-opus-4-6"
    verbosity: str = "brief"
    temperature: float = 0.7
    max_tokens: int = 1024
    zcode: ZCodeConfig = field(default_factory=ZCodeConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)


@dataclass
class RAGConfig:
    db_path: str = "data/knowledge_base"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    top_k_events: int = 3
    top_k_choices: int = 5
    similarity_threshold: float = 0.6


@dataclass
class PlayerConfig:
    """Player stats (maps from YAML player.stats.*)."""
    strength: int | None = None
    dex: int | None = None
    intelligence: int | None = None
    cha: int | None = None
    con: int | None = None
    wis: int | None = None


@dataclass
class Config:
    emulator: EmulatorConfig = field(default_factory=EmulatorConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    player: PlayerConfig = field(default_factory=PlayerConfig)
    log_level: str = "INFO"

    @classmethod
    def from_yaml(cls, path) -> "Config":
        """Load config from YAML file. Accepts str or pathlib.Path."""
        if isinstance(path, str):
            path = Path(path)
        if not isinstance(path, Path):
            return cls()
        if not path.exists():
            return cls()

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return cls()

        def _from_dict(cls_type, d):
            if not isinstance(d, dict):
                return cls_type()
            valid_keys = {f.name for f in fields(cls_type)}
            filtered = {k: v for k, v in d.items() if k in valid_keys}
            return cls_type(**filtered)

        # Player stats live under player.stats.* in the YAML.
        # Flatten into player_data so that YAML {stats: {str: null, dex: null}}
        # becomes {str: null, dex: null} and matches PlayerConfig field names.
        # Copy first to avoid mutating the parsed YAML dict.
        player_data = dict(data.get("player", {}))
        if "stats" in player_data and isinstance(player_data["stats"], dict):
            player_stats = dict(player_data.pop("stats"))
            player_data.update(player_stats)
        # Normalize YAML shorthand keys to PlayerConfig field names.
        _stat_alias = {"str": "strength"}
        for yaml_key, cfg_key in _stat_alias.items():
            if yaml_key in player_data and cfg_key not in player_data:
                player_data[cfg_key] = player_data.pop(yaml_key)

        # AI config: resolve nested provider configs into dataclass instances
        ai_data = data.get("ai", {})
        if isinstance(ai_data, dict):
            ai_top_level = {k: v for k, v in ai_data.items()
                            if k not in ("zcode", "openai", "ollama")}
            ai_nested = {
                "zcode": ZCodeConfig(**(ai_data.get("zcode") or {})),
                "openai": OpenAIConfig(**(ai_data.get("openai") or {})),
                "ollama": OllamaConfig(**(ai_data.get("ollama") or {})),
            }
            ai_config = _from_dict(AIConfig, {**ai_top_level, **ai_nested})
        else:
            ai_config = AIConfig()

        result = cls(
            emulator=_from_dict(EmulatorConfig, data.get("emulator", {})),
            overlay=_from_dict(OverlayConfig, data.get("overlay", {})),
            ai=ai_config,
            rag=_from_dict(RAGConfig, data.get("rag", {})),
            player=_from_dict(PlayerConfig, player_data if isinstance(player_data, dict) else {}),
            log_level=data.get("app", {}).get("log_level", "INFO"),
        )
        # Normalize YAML-loaded capture_region list → tuple
        result._normalize_capture_region()
        return result

    def _normalize_capture_region(self) -> None:
        """Normalize capture_region from YAML list to tuple."""
        region = getattr(self.emulator, "capture_region", None)
        if region is not None and isinstance(region, (list, tuple)) and len(region) == 4:
            try:
                self.emulator.capture_region = tuple(int(v) for v in region)
            except (ValueError, TypeError):
                self.emulator.capture_region = None

    def to_yaml(self, path: Path) -> None:
        """Save config to YAML file."""
        player_dict = self.player.__dict__.copy()
        # Un-nest stats back under player.stats for YAML compatibility
        # and convert field names to YAML shorthand (strength → str)
        stat_alias = {"strength": "str"}
        stat_keys = {"strength", "dex", "intelligence", "cha", "con", "wis"}
        player_stats = {}
        for k in list(player_dict.keys()):
            if k in stat_keys:
                yaml_key = stat_alias.get(k, k)
                player_stats[yaml_key] = player_dict.pop(k)
        player_data = {**player_dict, "stats": player_stats} if player_stats else player_dict

        data = {
            "emulator": self.emulator.__dict__,
            "overlay": self.overlay.__dict__,
            "ai": self.ai.__dict__,
            "rag": self.rag.__dict__,
            "player": player_data,
            "app": {"log_level": self.log_level},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False)

    def validate(self) -> List[str]:
        """
        Runtime config validation. Returns a list of warning/error strings.
        Empty list = all checks pass.
        """
        issues: List[str] = []

        # RAG thresholds
        if self.rag.similarity_threshold < 0.0 or self.rag.similarity_threshold > 1.0:
            issues.append(f"RAG similarity_threshold must be 0.0-1.0, got {self.rag.similarity_threshold}")
        if self.rag.top_k_events < 1 or self.rag.top_k_events > 20:
            issues.append(f"RAG top_k_events should be 1-20, got {self.rag.top_k_events}")

        # Capture interval
        if hasattr(self.emulator, "capture_interval"):
            ci = getattr(self.emulator, "capture_interval")
            if ci is not None and ci < 0.5:
                issues.append(f"capture_interval={ci}s is too aggressive (< 0.5s) — may overload CPU")
            if ci is not None and ci > 10.0:
                issues.append(f"capture_interval={ci}s is very slow (> 10s)")

        # Player stats: PlayerConfig fields are strength, dex, intelligence, cha, con, wis
        stat_keys = {"strength", "dex", "intelligence", "cha", "con", "wis"}
        for stat, val in vars(self.player).items():
            if stat in stat_keys and val is not None and not isinstance(val, (int, float)):
                issues.append(f"Player stat '{stat}' should be numeric, got {type(val).__name__}: {val}")

        return issues
