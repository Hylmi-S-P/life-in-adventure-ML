# Life in Adventure — AI Quest Assistant

> 🤖 An overlay companion tool that recognizes quests, shows choice outcomes, and provides AI-powered recommendations for Life in Adventure text-based RPG.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-blue.svg)](https://microsoft.com/windows)

---

## 🎯 What Is This?

**Life in Adventure** is a text-based D&D-style fantasy RPG by [Studio Wheel](https://play.google.com/store/apps/details?id=com.StudioWheel.Bard). Every choice you make is influenced by 6 stats (STR, DEX, INT, CHA, CON, WIS), past decisions, alignment, and dice rolls.

This tool is an **overlay assistant** that:

- Captures your game screen automatically (MuMuPlayer emulator)
- Extracts quest text via OCR
- Matches it against a local RAG knowledge base
- Provides AI-powered choice recommendations via ZCode/Claude API

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   MuMuPlayer        │     │  Overlay Tool    │     │  AI Engine      │
│   Life in Adventure │────►│  OCR + RAG       │────►│  (ZCode API)    │
│   (game running)    │cap  │  (local)         │query│                 │
│                     │◄────│  (local)         │◄────│                 │
└─────────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## ✨ Features

> **Documentation Review Complete (2026-07-06)**: See `docs/review/REVIEW_REPORT.md` for 5 critical findings (C1-C5) — all patched. Run `docs/review/review_prompt_v2.md` for formal validation.

### MVP Features (Phase 1)
- [ ] **Screen Capture Loop** — Auto-screenshot MuMuPlayer (adaptive interval 1-6s per I2)
- [ ] **OCR Engine** — Extract text from game screenshots (EasyOCR, multilingual pending per L1)
- [ ] **Quest Recognition** — Match extracted text to knowledge base via ChromaDB
- [ ] **Choice Outcome Display** — Show potential results for each option (includes `exp_delta` per C1)
- [ ] **AI Recommendation** — Claude-powered choice suggestions based on stats + EXP management per C1
- [ ] **Overlay Panel UI** — Semi-transparent panel floating over emulator

### Post-MVP Roadmap
- [ ] Player stat input panel
- [ ] Quest progress tracker
- [ ] Epilogue/unlocking tracker
- [ ] Community data contribution pipeline
- [ ] APK version diffing for KB updates
- [ ] Multi-language support (EN/KR/ID)

---

## 🏗️ Tech Stack

| Layer | Technology | Why |
|-------|------------|-----|
| **Language** | Python 3.11+ | Mature ML/OCR ecosystem |
| **Screen Capture** | `mss` + `pywin32` | Fast window capture; absolute screen coords for clicks |
| **OCR** | `EasyOCR` | Pixel-art fonts; KO/EN ROI crop; single-pass extract |
| **RAG / Vector** | `LlamaIndex` + `ChromaDB` + RapidFuzz + TF-IDF | Cascade hybrid search; LlamaIndex manages embed/index lifecycle |
| **Embedding** | `sentence-transformers` via LlamaIndex `HuggingFaceEmbedding` | `all-MiniLM-L6-v2`, CPU-friendly |
| **Decision** | HeuristicPolicy + PPO fallback | Offline scoring; low-confidence uses ActorCritic `.pt` or SB3 `.zip` |
| **RL Training** | `stable-baselines3` PPO | Replaces custom training loop; Gymnasium env + DummyVecEnv |
| **AI LLM (optional)** | ZCode / OpenAI / Ollama | Cloud or local narrative assist |
| **Overlay UI** | `customtkinter` | Always-on-top transparent panel |
| **APK Extraction** | `jadx` + asset JSON dump | Offline KB from game data |

---

## 📁 Project Structure

```
LifeInAdventure-Tools/
├── docs/                    # PRD, architecture, schema, setup
├── src/
│   ├── capture/             # Screen capture, auto-clicker, session logger
│   ├── ocr/                 # EasyOCR + normalizer
│   ├── rag/                 # KnowledgeBase (LlamaIndex+Chroma) + RAGRetriever
│   ├── ai/                  # Decision engine, HeuristicPolicy, RLTrainer (SB3)
│   ├── core/                # Thread-safe state, cache, metrics, dedup
│   ├── ui/                  # Overlay, stats, settings, feedback
│   └── data_extraction/     # APK asset extract
├── configs/default_config.yaml
├── tests/                   # e2e + session logger (17 tests)
├── data/                    # Local only (gitignored): KB, models, sessions
├── README.md
├── SPEC.md
├── requirements.txt
└── .gitignore
```

---

## 🚀 Quick Start

### Prerequisites

- **Windows 10/11** (primary target)
- **Python 3.11+**
- **MuMuPlayer** with Life in Adventure installed
- **ZCode API key** (optional — tool works with community data fallback)

### 1. Clone & Setup Environment

```bash
git clone https://github.com/Hylmi-S-P/life-in-adventure-ML.git
cd life-in-adventure-ML

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt
```

### 2. Download APK & Extract Game Data

```bash
# Download APK from APKMirror (or extract from installed app)
# Place APK in data/raw_extracted/

# Extract game data
python scripts/extract_apk.py --apk "data/raw_extracted/life-in-adventure.apk"

# Build knowledge base
python scripts/first_time_setup.py --version "1.2.42"
```

### 3. Configure

Edit `configs/default_config.yaml`:

```yaml
emulator:
  type: "mumuproplayer"
  capture_interval: 3  # seconds

overlay:
  position: "right"
  opacity: 0.85
  width: 450
  height: 600

ai:
  provider: "zcode"  # or "openai", "ollama"
  verbosity: "brief"  # brief | detailed | expert

knowledge_base:
  path: "data/knowledge_base"
  version: "1.2.42"
```

### 4. Run

```bash
python src/main.py
```

The overlay will appear. Make sure MuMuPlayer is running Life in Adventure alongside it.

---

## 🔧 Configuration

See [docs/setup/SETUP_GUIDE.md](docs/setup/SETUP_GUIDE.md) for full setup instructions.

Key settings in `configs/default_config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `emulator.type` | `mumuproplayer` | Emulator type |
| `emulator.capture_interval` | `3` | Screenshot frequency (seconds) |
| `overlay.position` | `right` | Screen position |
| `overlay.opacity` | `0.85` | Panel transparency (0-1) |
| `ai.verbosity` | `brief` | Response detail level |
| `ai.model` | `claude-opus-4-6` | AI model via ZCode |

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [PRD](docs/prd/PRD.md) | Product Requirements — vision, goals, features |
| [SPEC.md](SPEC.md) | Technical Specification — architecture, components, contracts |
| [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | Deep-dive system architecture |
| [SETUP_GUIDE.md](docs/setup/SETUP_GUIDE.md) | Step-by-step installation guide |
| [DATA_SCHEMA.md](docs/data/DATA_SCHEMA.md) | Knowledge base data schema |
| [API_CONTRACT.md](docs/api/API_CONTRACT.md) | AI engine interface contract |

---

## 🎮 Game Info

| Item | Detail |
|------|--------|
| **Developer** | Studio Wheel (Busan, South Korea) |
| **Package** | `com.StudioWheel.Bard` |
| **Platforms** | Android, iOS, Windows (via Play Games) |
| **Genre** | Text-based RPG / Choose Your Own Adventure |
| **Latest Version** | 1.2.42 (February 2026) |
| **Community** | [Discord](https://discord.gg/9JdYkGm2T3) · [Reddit](https://reddit.com/r/LifeInAdventure) · [Fandom Wiki](https://life-in-adventure.fandom.com) |

---

## 🤝 Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting.

Ways to contribute:
- Report bugs via GitHub Issues
- Submit quest/outcome data to expand the knowledge base
- Improve OCR accuracy for game fonts
- Translate documentation
- Test on different emulator configurations

---

## ⚠️ Disclaimer

This tool is for **educational and personal use** only. It is not affiliated with Studio Wheel. Respect the game's terms of service. Data extraction is performed on your own installed copy of the game.

---

## 📄 License

MIT License — see [LICENSE](LICENSE).

*Built with 💜 for the Life in Adventure community.*
