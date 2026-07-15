# Setup Guide

> Step-by-step installation and setup for LifeInAdventure-Tools.
> Estimated time: **30-60 minutes** (first time only)

---

## Prerequisites

Before starting, ensure you have:

| Requirement | Minimum | Recommended | Check |
|------------|---------|-------------|-------|
| **OS** | Windows 10 | Windows 11 | `winver` |
| **RAM** | 8 GB | 16 GB | `systeminfo \| findstr Memory` |
| **Disk** | 5 GB free | 10 GB free | `wmic logicaldisk get size,freespace` |
| **Python** | 3.11 | 3.12+ | `python --version` |
| **MuMuPlayer** | Latest | Latest | [Download](https://mumu.163.com/) |
| **Life in Adventure** | Installed | Latest version | Open from MuMuPlayer |

### Check Python Version

```bash
# Open Git Bash or Command Prompt
python --version
# Should output Python 3.11 or higher

# If not installed, download from https://python.org
# IMPORTANT: Check "Add Python to PATH" during installation
```

---

## Step 1: Environment Setup

### 1.1 Clone Repository

```bash
# Open Git Bash in your desired directory
cd D:/

# Clone the repository (or copy manually)
git clone https://github.com/yourusername/LifeInAdventure-Tools.git
cd LifeInAdventure-Tools
```

### 1.2 Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows Git Bash:
source venv/Scripts/activate

# Windows CMD:
# venv\Scripts\activate.bat

# Windows PowerShell:
# venv\Scripts\Activate.ps1
```

### 1.3 Install Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt

# This installs:
# - mss (screen capture)
# - Pillow (image processing)
# - EasyOCR (text recognition)
# - chromadb (vector database)
# - sentence-transformers (embeddings)
# - anthropic (Claude API)
# - customtkinter (UI)
# - PyYAML (config)
# - pywin32 (Windows API)
```

> **Note**: EasyOCR download will fetch ML models (~500MB) on first run.
> This is normal. Requires internet connection.

### 1.4 Verify Installation

```bash
# Quick sanity check
python -c "
import mss; import PIL; import easyocr; import chromadb
import sentence_transformers; import anthropic
print('All packages OK!')
"
```

---

## Step 2: MuMuPlayer Setup

### 2.1 Install MuMuPlayer

1. Download from [mumu.163.com](https://mumu.163.com/)
2. Install with default options
3. Open MuMuPlayer and complete initial setup (Google account if needed)
4. **Install Life in Adventure**:
   - Open Google Play Store in MuMuPlayer
   - Search "Life in Adventure Studio Wheel"
   - Install

### 2.2 Configure MuMuPlayer Settings

For best screen capture results:

```
MuMuPlayer Settings → General:
├─ Performance Mode: [Standard] or [Performance]
├─ Resolution: [1280x720] (lower = faster OCR)
├─ FPS: [60] (default)
└─ [x] Enable root access (optional, not required)

MuMuPlayer Settings → Display:
└─ [x] High DPI scaling (disable if overlay misaligns)
```

### 2.3 Test MuMuPlayer Window

```bash
# Run this to verify MuMuPlayer is detected
python -c "
from src.capture.emulator_detector import detect_emulator
try:
    emulator = detect_emulator()
    print(f'Detected: {emulator}')
except Exception as e:
    print(f'Not detected: {e}')
    print('Make sure MuMuPlayer is running with Life in Adventure open.')
"
```

---

## Step 3: APK Data Extraction (Optional but Recommended)

This step extracts game data to build the knowledge base.
**Without this, the tool falls back to basic RAG with limited coverage.**

### 3.1 Install Java (Required for jadx)

jadx requires Java 11+.

```bash
# Check if Java is installed
java -version 2>&1

# If not installed:
# Download from https://adoptium.net/ (Temurin JDK 17 recommended)
# Install and add to PATH
```

### 3.2 Download APK

**Option A: From installed app (Recommended)**

```bash
# Use ADB to pull APK from MuMuPlayer
adb connect 127.0.0.1:16384  # Default MuMuPlayer port
adb shell pm path com.StudioWheel.Bard
adb pull <apk_path> data/raw_extracted/life-in-adventure.apk
```

**Option B: Download from APKMirror**

1. Visit [APKMirror](https://www.apkmirror.com)
2. Search "Life in Adventure"
3. Download latest version APK
4. Move to `data/raw_extracted/life-in-adventure.apk`

### 3.3 Run Extraction

```bash
# Extract game data
python scripts/extract_apk.py --apk data/raw_extracted/life-in-adventure.apk

# Expected output:
# [1/4] Decompiling APK with jadx...
# [2/4] Extracting Unity assets...
# [3/4] Parsing game data files...
# [4/4] Building knowledge base...
#
# Extraction complete!
# Quests: 47 | Events: 892 | Choices: 1,203 | Epilogues: 89
# Knowledge base saved to: data/knowledge_base/
```

> **Troubleshooting**:
> - If extraction fails at jadx: Verify Java is in PATH
> - If assets empty: Game might use encrypted assets — see Section 3.4

### 3.4 APK Extraction Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| `jadx: command not found` | jadx not installed | Download from [github.com/skylot/jadx](https://github.com/skylot/jadx/releases) |
| Empty assets folder | Encrypted Unity assets | Use il2cppdumper or fall back to community data |
| `Parse error: line 1` | Binary/encrypted file | Skip file, continue with others |
| APK download fails | APKMirror anti-bot | Use Option A (pull from device) |

### 3.5 If APK Extraction Fails

**Fallback: Build KB from community sources**

```bash
# Manually place game data files (JSON) in:
data/parsed/

# Then build KB from parsed files:
python scripts/first_time_setup.py --source data/parsed/ --version "1.2.42"
```

Community data sources:
- [r/LifeInAdventure](https://reddit.com/r/LifeInAdventure) — guide v2.0
- [Life in Adventure Wiki](https://life-in-adventure.fandom.com/) — epilogues, items
- [Scribd Guide](https://www.scribd.com/document/607016681/) — comprehensive guide

---

## Step 4: Configure Settings

### 4.1 Copy Default Config

```bash
cp configs/default_config.yaml configs/local_config.yaml
```

### 4.2 Edit Configuration

```yaml
# configs/local_config.yaml

# Emulator — should auto-detect, but can override
emulator:
  type: "mumuproplayer"
  capture_interval: 3.0

# AI Engine — ZCode should work by default
ai:
  provider: "zcode"
  model: "claude-opus-4-6"
  # API key: Leave empty — uses ZCode from environment
  # ZCODE_API_KEY env var should be picked up automatically

# Knowledge Base
knowledge_base:
  version: "1.2.42"  # Update after APK extraction
```

### 4.3 Environment Variables (Optional)

Create `.env` file in project root:

```bash
# .env
ZCODE_API_KEY=your_zcode_key_here  # Optional — usually auto-detected
LIA_CONFIG_PATH=configs/local_config.yaml
LIA_LOG_LEVEL=INFO
```

---

## Step 5: Initial Knowledge Base Build

> **Note (C4)**: Knowledge base size is estimated at **~1,000–3,000 events** total (main + side quests + random events).
> KB build time scales with event count; first build may take 5–15 minutes depending on ChromaDB indexing.
> See `docs/data/DATA_SCHEMA.md` for schema details and `docs/review/REVIEW_REPORT.md` for estimate rationale.


```bash
# Run first-time setup (build ChromaDB from parsed data)
python scripts/first_time_setup.py --version "1.2.42"

# Output should show:
# ==============================================
# Life in Adventure — First Time Setup
# ==============================================
# Version: 1.2.42
# Source: data/parsed/
# Target: data/knowledge_base/
#
# Building embeddings...
# [████████████] 100% | 1,203 choices
#
# ChromaDB collections created:
#   quests:     47 entries
#   events:    892 entries
#   choices: 1,203 entries
#   epilogues:  89 entries
#
# Build complete! Total time: ~2 minutes
#
# Next step: Run `python src/main.py` to start the assistant
```

---

## Step 6: Run the Tool

### 6.1 Basic Launch

```bash
# Make sure MuMuPlayer is running with Life in Adventure open
python src/main.py
```

You should see:
1. A semi-transparent overlay panel appear
2. The overlay says "Initializing..." (first run: downloading ML models)
3. After ~1-2 minutes, overlay shows "Ready — No quest detected"
4. Navigate in-game to any quest → overlay should update automatically

### 6.2 First Run Tips

| Tip | Description |
|-----|-------------|
| **First OCR takes long** | EasyOCR downloads models on first run (500MB). Subsequent runs are fast. |
| **Overlay position** | Drag the overlay to any position. It will remember the last position. |
| **F9 to toggle** | Press F9 to hide/show overlay. Useful during combat. |
| **Settings F11** | Press F11 to open settings panel. |
| **Log file** | Check `logs/app.log` if something goes wrong. |

### 6.3 Configuration Hot Reload

You can edit `configs/local_config.yaml` while the tool is running.
Press **F10** to reload configuration without restarting.

---

## Step 7: Fine-Tuning (Post-MVP)

### 7.1 Improve OCR Accuracy

```bash
# If OCR is struggling with game font, collect more screenshots:
mkdir -p tests/fixtures/screenshots
# Add screenshots of various game screens
# This helps calibrate EasyOCR model weights

# Run OCR accuracy test:
python tests/test_ocr.py --fixtures tests/fixtures/
```

### 7.2 Expand Knowledge Base

```bash
# Add community-contributed quest data:
# 1. Place JSON files in data/parsed/contrib/
# 2. Validate schema:
python scripts/validate_data.py --dir data/parsed/contrib/

# 3. Merge into KB:
python scripts/merge_kb.py --source data/parsed/contrib/
```

### 7.3 Update KB for New Game Version

```bash
# When a new game version is released:
# 1. Download new APK
python scripts/extract_apk.py --apk data/raw_extracted/life-in-adventure-NEW.apk

# 2. Diff with old version:
python scripts/diff_versions.py --old 1.2.42 --new 1.2.43

# 3. Apply only changed entries:
python scripts/apply_diff.py --diff changes.json

# 4. Rebuild KB with new data:
python scripts/first_time_setup.py --version "1.2.43"
```

---

## Step 8: Uninstall

```bash
# Deactivate virtual environment
deactivate

# Delete virtual environment (optional)
rm -rf venv/

# Remove logs (optional)
rm -rf logs/

# Uninstall packages (optional, if you used system Python)
pip uninstall -r requirements.txt -y
```

---

## Quick Reference — Command Cheatsheet

| Command | Purpose |
|---------|---------|
| `pip install -r requirements.txt` | Install dependencies |
| `python scripts/extract_apk.py --apk <path>` | Extract game data |
| `python scripts/first_time_setup.py` | Build knowledge base |
| `python src/main.py` | Launch overlay tool |
| `F9` | Toggle overlay visibility |
| `F10` | Reload configuration |
| `F11` | Open settings panel |
| `F12` | Quit application |

---

## Troubleshooting Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| MuMuPlayer not detected | Verify MuMuPlayer is running, try `type: "mumuproplayer"` in config |
| Overlay not visible | Press F9, check if behind game window |
| OCR text garbled | Lower capture_interval to 5s, or resize emulator to 1280x720 |
| AI not responding | Check internet connection, ZCode API key |
| KB empty / no matches | Run `scripts/first_time_setup.py` first |
| ChromaDB lock error | Delete `data/knowledge_base/chroma.sqlite`, rebuild KB |
| EasyOCR model download fail | Check internet, models auto-retry on next run |

---

*End of SETUP_GUIDE.md*
