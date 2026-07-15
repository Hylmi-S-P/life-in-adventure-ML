# Architecture Deep Dive

> Detailed technical architecture for LifeInAdventure-Tools.
> 
> **v1.2** (2026-07-16): Framework migration notes:
> - RAG: LlamaIndex indexes embeddings into Chroma; retrieval cascade remains RapidFuzz → TF-IDF → Chroma
> - RL: Stable-Baselines3 PPO for training (`rl_trainer.py`); live PPO fallback still uses ActorCritic `.pt` or SB3 `.zip`
> 
> **v1.1** (2026-07-06): Patches per `docs/review/REVIEW_REPORT.md`:
> - M6: ZCode base_url align dengan SPEC/API_CONTRACT (`gateway.olagon.site`)
> - I4: EventBus interface sketch code added (§1.2)
> - I2: Capture optimizations + adaptive interval callout
> - C5: IL2CPP risk acknowledgement (§7.1)
> 
> Read [SPEC.md](../../SPEC.md) for high-level overview first.

---

## 1. System Architecture

### 1.1 Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PRESENTATION LAYER                             │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────────────┐ │
│  │  Overlay Panel  │  │  Settings Panel   │  │  System Tray / Hotkeys    │ │
│  │  (customtkinter)│  │  (config UI)     │  │  (background controls)    │ │
│  └────────┬────────┘  └────────┬─────────┘  └─────────────┬──────────────┘ │
│           │                    │                            │               │
│           └────────────────────┼────────────────────────────┘               │
│                                │                                            │
│  ┌─────────────────────────────▼─────────────────────────────────────────┐ │
│  │                    EVENT / MESSAGE BUS                                  │ │
│  │  (Internal pub/sub for loose coupling between components)               │ │
│  └─────────────────────────────┬─────────────────────────────────────────┘ │
└────────────────────────────────┼──────────────────────────────────────────┘
                                 │
┌────────────────────────────────┼──────────────────────────────────────────┐
│                           BUSINESS LOGIC LAYER                             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌─────────────────┐   │
│  │   Screen   │  │    OCR     │  │    RAG     │  │    AI Engine    │   │
│  │  Capture   │─►│  Processing│─►│  Retrieval │─►│  Decision       │   │
│  │  Module    │  │  Module    │  │  Module    │  │  Engine         │   │
│  └────────────┘  └────────────┘  └────────────┘  └────────┬────────┘   │
│                                                             │              │
│  ┌──────────────────────────────────────────────────────────┴───────────┐ │
│  │                    GAME STATE MANAGER                                 │ │
│  │  - Tracks current quest, player stats, visited events                 │ │
│  │  - Manages state transitions between capture cycles                   │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────┼──────────────────────────────────────────┐
│                              DATA LAYER                                    │
│  ┌────────────────┐  ┌────────────────────┐  ┌─────────────────────────┐   │
│  │ SQLite + Chroma│  │   Parsed JSON      │  │   Configuration         │   │
│  │ (LlamaIndex    │  │   Game Data        │  │   (YAML)               │   │
│  │  embed/index)  │  │                    │  │                         │   │
│  └───────┬────────┘  └─────────┬──────────┘  └─────────────────────────┘   │
│          │                      │                                          │
│          ▼                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                  APK EXTRACTION PIPELINE                              │ │
│  │  APK → jadx → assets_dump JSON → SQLite ingest → LlamaIndex/Chroma  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│  Offline RL: CuriosityAdventureEnv → SB3 DummyVecEnv → PPO (rl_trainer)  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Message Bus Implementation

Components communicate via a lightweight **EventBus** for loose coupling between pipe stages:

```python
class EventBus:
    """
    Simple pub/sub event bus with async support. Avoids tight coupling between
    capture, OCR, RAG, AI, and overlay modules. Sources:

    - capture: emit 'screen_captured' (PIL.Image)
    - ocr: emit 'ocr_completed' (OcrResult)
    - rag: emit 'rag_completed' (GameStateContext)
    - ai: emit 'recommendation_ready' (AIRecommendation)
    """
    def __init__(self):
        self._handlers = defaultdict(list)
        self._async_loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_async, daemon=True).start()

    def _run_async(self):
        asyncio.set_event_loop(self._async_loop)
        self._async_loop.run_forever()

    def subscribe(self, event: str, handler: Callable, async_mode=False):
        self._handlers[event].append((handler, async_mode))
        if async_mode:
            handler = partial(self._async_run, handler=handler)
        return lambda: self._handlers[event].remove((handler, async_mode))

    def publish(self, event: str, *args, **kwargs):
        for handler, async_mode in self._handlers.get(event, []):
            if async_mode:
                asyncio.run_coroutine_threadsafe(handler(*args, **kwargs), self._async_loop)
            else:
                try:
                    handler(*args, **kwargs)
                except Exception as e:
                    loguru.logger.error(f"EventBus error on {event}: {e}")

    async def _async_run(self, handler, *args, **kwargs):
        try:
            await handler(*args, **kwargs)
        except Exception as e:
            loguru.logger.error(f"EventBus async error on {handler.__name__}: {e}")

# Singleton instance
event_bus = EventBus()

# Events
EVENT_CAPTURED = "screen_captured"
EVENT_OCR_COMPLETED = "ocr_completed"
EVENT_RAG_MATCHED = "rag_completed"
EVENT_AI_RESPONSE = "ai_completed"
EVENT_CONFIG_CHANGED = "config_changed"
EVENT_OVERLAY_READY = "overlay_ready"
EVENT_SHUTDOWN = "shutdown"
```

Usage Example from `ScreenCapture`:

```python
def capture_loop(self):
    while self._running:
        try:
            img = self._capture_window()
            if not self_text_normalizer.is_duplicate(img):
                event_bus.publish(EVENT_CAPTURED, img)
            time.sleep(self._interval)
        except CaptureError as e:
            raise e
```

---

## 2. Screen Capture Deep Dive

### 2.1 MuMuPlayer-Specific Handling

MuMuPlayer (Netease's Android emulator) has unique characteristics:

| Aspect | MuMuPlayer Behavior |
|--------|---------------------|
| **Window Title** | `"MuMu"` / `"MuMu Player"` / `"Nemu"` |
| **Render Method** | DirectX/Vulkan (hardware accelerated) |
| **Screenshot Method** | `mss` with `monitor` mode works well |
| **Multi-instance** | Supports multiple instances (port-based) |
| **API** | MuMu SDK available but undocumented |
| **ADB Port** | Default `127.0.0.1:16384` |

### 2.2 Capture Pipeline

```python
# capture/screen_capture.py — simplified flow

def capture_loop():
    """
    Background thread loop:
    1. Wait for capture_interval
    2. Capture full window screenshot
    3. Optionally crop to game region (remove emulator chrome)
    4. Preprocess image (grayscale, contrast enhancement)
    5. Check for duplicate (skip if same as previous)
    6. Publish "screen_captured" event
    7. Notify UI of capture status
    """

    SCREENSHOT_CANDIDATES = [
        # Method 1: mss window capture (fastest, works on most emulators)
        lambda: mss.mss().grab(monitor),

        # Method 2: Win32 PrintWindow (if mss fails)
        lambda: win32gui.PrintWindow(hwnd, hdcDest, 2),

        # Method 3: DirectX texture capture (fallback, MuMu-specific)
        lambda: dx_capture.get_frame(),
    ]
```

### 2.3 Performance Optimizations

```python
# Capture optimizations:
1. RESIZE_DOWN: Scale 1920x1080 → 960x540 for OCR (4x faster)
2. GRAYSCALE_CONVERT: Color → Grayscale (1/3 data, OCR doesn't need color)
3. SKIP_IF_IDENTICAL: Hash-based dedup — skip if frame == previous frame
4. ASYNC_CAPTURE: Capture in background thread, OCR in main thread
5. CACHE_CAPTURE: Keep last N frames for debug/retry
```

---

## 3. OCR Pipeline Deep Dive

### 3.1 Why EasyOCR Over Tesseract?

| Criteria | EasyOCR | Tesseract | Winner |
|----------|---------|-----------|--------|
| Game font handling | ✅ Custom-trained models | ⚠️ Needs training | EasyOCR |
| Multi-language | ✅ EN+KO+ID built-in | ✅ Good for EN | Tie |
| Speed (CPU) | ~1-2s per frame | ~0.5-1s per frame | Tesseract |
| Accuracy (pixel art) | ✅ Better | ❌ Poor | EasyOCR |
| Python integration | ✅ Native | ⚠️ via pytesseract | EasyOCR |
| Memory usage | ~500MB | ~50MB | Tesseract |

**Decision**: EasyOCR with `en` + `ko` language packs for MVP.
Fallback to Tesseract if EasyOCR fails repeatedly.

### 3.2 Game-Specific OCR Tuning

```python
# OCR preprocessing for game text:
PREPROCESS_STEPS = [
    ("grayscale", lambda img: img.convert("L")),
    ("contrast", lambda img: ImageOps.autocontrast(img, cutoff=2)),
    ("denoise", lambda img: img.filter(ImageFilter.MedianFilter(size=3))),
    ("sharpen", lambda img: img.filter(ImageFilter.SHARPEN)),
    ("resize", lambda img: img.resize((img.width * 2, img.height * 2), LANCZOS)),
]
```

### 3.3 Text Parsing Heuristics

```python
# Quest text structure (from game observation):
# ─────────────────────────────────────────────────────────
# [QUEST TITLE]                                    [PROGRESS]
# ─────────────────────────────────────────────────────────
# Narrative text describing the current situation...
# More narrative text...
# ─────────────────────────────────────────────────────────
# [A] Choice option text
# [B] Choice option text
# [C] Choice option text
# ─────────────────────────────────────────────────────────
# HP: ████████░░ 80/100  |  EXP: ██░░░░░░░░ 18%  |  LV: 5

# Parsing rules:
# 1. Quest title: Text before first "─" or large text block
# 2. Choices: Lines starting with "[A]", "[B]", "[C]", "[D]" or "• "
# 3. Stats: Text matching HP/EXP/LV patterns
# 4. Progress: Text before "─" at top-right
```

---

## 4. RAG Architecture Deep Dive

### 4.1 Why ChromaDB?

| Criteria | ChromaDB | FAISS | Qdrant | LanceDB |
|----------|----------|-------|--------|---------|
| Setup | Zero-config | Requires index build | Needs server/container | File-based |
| Persistence | SQLite file | File | Docker | File |
| Python-native | ✅ Native | ⚠️ via numpy | ⚠️ gRPC | ✅ Native |
| Filtering | Metadata filter | ⚠️ Limited | ✅ Full | ✅ Full |
| Updates | ⚠️ Append-only | ❌ Rebuild | ✅ CRUD | ✅ CRUD |
| Size limit | ~100K vectors | No limit | No limit | No limit |
| Speed | Fast | Fastest | Fast | Fast |

**Decision**: ChromaDB for MVP (zero-config, file-based, sufficient for ~5K events).

### 4.2 Embedding Strategy

```python
# Embedding strategy per collection:

EMBEDDING_CONFIGS = {
    "quests": {
        "text": lambda q: f"{q.title}. {q.description}. "
                          f"Location: {q.location}. Type: {q.type}. "
                          f"Tier: {q.tier}",
        "top_k": 3,
    },
    "events": {
        "text": lambda e: f"{e.text} "
                          f"Choices: {' '.join(c.text for c in e.choices)}",
        "top_k": 5,
    },
    "choices": {
        "text": lambda c: f"{c.text} "
                          f"Requirements: {c.stat_check.description if c.stat_check else 'None'} "
                          f"Outcomes: {' '.join(o.result for o in c.outcomes)}",
        "top_k": 3,
    },
    "epilogues": {
        "text": lambda ep: f"{ep.name}. {ep.description}. "
                           f"Requirements: {' '.join(ep.requirements)}",
        "top_k": 5,
    },
}

# Model: all-MiniLM-L6-v2 (384-dim)
# - 22M params, fast on CPU
# - 384 dimensions, good for semantic search
# - Trained on sentence pairs, strong for retrieval
```

### 4.3 Retrieval Pipeline

```
User screenshot text
        │
        ▼
┌───────────────────┐
│  Semantic Search  │ ← ChromaDB similarity search (all 4 collections)
│  (top_k per col)  │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│   Meta-filtering  │ ← Filter by: game version, language, quest type
│  (context-aware)  │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Score merging    │ ← Weighted combination: event > choice > quest > epilogue
│  (reranking)     │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│ Context Assembly │ ← Package into GameStateContext
│                  │
└───────────────────┘
```

### 4.4 Knowledge Base Schema Design

See [docs/data/DATA_SCHEMA.md](DATA_SCHEMA.md) for full schema.

**Key design decisions**:
- **Event-first design**: Events are the primary unit, not quests
  - Reason: Same quest can appear in different contexts; event text is more specific
- **Stat checks as first-class**: Each choice has explicit stat requirements
  - Reason: AI engine needs this to give informed recommendations
- **Outcome graph**: Outcomes link to other events, items, epilogues
  - Reason: Enables traversal and consequence tracking
- **Background-aware**: Quests tagged with which backgrounds affect them
  - Reason: Critical for understanding alternate storylines

---

## 5. AI Decision Engine Deep Dive

### 5.1 AI Decision Engine Configuration

```python
PROVIDER_CONFIGS = {
    "zcode": {
        "client": "anthropic.Anthropic",
        "base_url": "https://gateway.olagon.site/anthropic", # Aligned with SPEC §2.1 + API_CONTRACT §2.1
        "default_model": "claude-opus-4-6",
        "api_key": lambda: os.getenv("ZCODE_API_KEY"), # Or resolve via nested config.py ZCodeConfig
        "is_local": False
    },
    "openai": {
        "client": "openai.OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "api_key": lambda: os.getenv("OPENAI_API_KEY"),
        "is_local": False
    },
    "ollama": {
        "client": "openai.OpenAI",
        "base_url": "http://localhost:11434",
        "default_model": "llama3.2",
        "api_key": lambda: None,
        "is_local": True
    },
}
```

Provider selection per AI config:

```python
provider = PROVIDER_CONFIGS[config.ai.provider]
client = provider["client"](base_url=provider["base_url"], api_key=provider["api_key"]())
```

### 5.2 Prompt Engineering Strategy

```python
# Multi-shot prompting with RAG context injection:

PROMPT_TEMPLATE = """\
## SYSTEM
You are a tactical advisor for the text-based RPG "Life in Adventure".
You provide concise, strategic recommendations based on game mechanics.

## GAME CONTEXT
Current Game Version: {version}
Player Stats: {player_stats}
Player Level: {level}
Alignment: {alignment}  # -100 (chaotic) to +100 (lawful)
Gold: {gold}

## CURRENT QUEST
Quest: {quest_title}
Type: {quest_type} | Tier: {quest_tier}
Location: {location}
Description: {quest_description}

## AVAILABLE CHOICES
{choices_block}

## KNOWLEDGE BASE CONTEXT
(Retrieved from game database)
{kb_context}

## OUTPUT FORMAT
For each choice, give:
- **Choice**: [letter]
- **Stat Check**: stat + threshold (if any)
- **Best For**: what this choice excels at
- **Risks**: potential negative outcomes
- **Outcome Preview**: likely result summary

Then give your recommendation with reasoning.

Be brief. Max 200 words total.\
"""
```

### 5.3 Response Caching

```python
# LRU cache for AI responses:
# Key: hash(quest_text + normalized_choices + player_stats)
# Value: AIRecommendation

# Cache strategy:
# - Size: 100 entries max (LRU eviction)
# - TTL: 5 minutes (game state can change)
# - Scope: Same quest text + choices = same recommendation
#   (player stats vary, so cache by quest+choices only)

# Tiered response:
# 1. Cache hit → instant response (< 50ms)
# 2. Cache miss → API call with "brief" mode
# 3. API timeout → show RAG-only data (no AI)
# 4. Full offline → show knowledge base data only
```

---

## 6. Overlay UI Deep Dive

### 6.1 Window Configuration (Windows)

```python
# Overlay window setup for customtkinter on Windows:
window.configure(fg_color="#1a1a2e")  # Background color
window.attributes("-topmost", True)  # Always on top
window.attributes("-transparentcolor", "black")  # Transparency key
window.overrideredirect(True)  # Remove window frame

# For click-through on specific regions:
# - Title bar area: clicks pass through
# - Content area: draggable
# - Settings button: clickable
```

### 6.2 Layout Structure

```
┌──────────────────────────────────────────────────┐
│ [≡] Life in Adventure    Quest Assistant  [—][×] │  ← Custom title bar (draggable)
├──────────────────────────────────────────────────┤
│                                                  │
│  📖 QUEST NAME                            ████░ │  ← Quest title + progress
│  ─────────────────────────────────────────────── │
│  Quest description text...                       │
│                                                  │
│  ┌─ AVAILABLE CHOICES ───────────────────────┐  │
│  │ [A] Choice text here                      │  │
│  │     Stat: DEX 5+ | Success: ...           │  │
│  │     Outcome preview...                     │  │
│  │                                           │  │
│  │ [B] Another choice                        │  │
│  │     No stat check | Outcome...            │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
│  ┌─ AI RECOMMENDATION ───────────────────────┐  │
│  │ 🏆 [A] Best — highest reward potential    │  │
│  │ 💡 Tip: Your DEX is high, go for it!      │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
├──────────────────────────────────────────────────┤
│ ⚙ STR:8 DEX:6 INT:5 CHA:4 │ v1.2.42 │ [F9]pause│  ← Status bar
└──────────────────────────────────────────────────┘
```

### 6.3 Theming

```python
THEMES = {
    "dark": {
        "bg": "#1a1a2e",
        "surface": "#16213e",
        "text": "#e0e0e0",
        "accent": "#00d4ff",
        "success": "#4ade80",
        "danger": "#f87171",
        "warning": "#fbbf24",
    },
    "light": {
        "bg": "#f0f4f8",
        "surface": "#ffffff",
        "text": "#1a1a2e",
        "accent": "#0066cc",
        "success": "#16a34a",
        "danger": "#dc2626",
        "warning": "#d97706",
    },
    "amoled": {
        "bg": "#000000",
        "surface": "#0a0a0a",
        "text": "#cccccc",
        "accent": "#00ffff",
        "success": "#00ff88",
        "danger": "#ff4444",
        "warning": "#ffaa00",
    },
}
```

---

## 7. APK Extraction Deep Dive

### 7.1 Engine Detection

```python
def detect_engine(apk_path: str) -> str:
    """
    Life in Adventure uses Unity engine (confirmed from:
    - APK uses Unity classes)
    - Build targets Android
    - Package: com.StudioWheel.Bard

    Detection methods:
    1. Check for libunity.so in lib/ directory
    2. Check for classes.dex (mono) vs libil2cpp.so (IL2CPP)
    3. Check AndroidManifest.xml for Unity metadata
    """
```

### 7.2 Data File Locations

```
After jadx decompilation:

life-in-adventure/
├── sources/
│   └── com.StudioWheel.Bard/
│       └── ...  (Java/Kotlin source — mostly Unity glue)
├── assets/
│   ├── bin/
│   │   └── Data/
│   │       ├── globalgamemanagers      (Unity asset bundles)
│   │       ├── globalgamemanagers.assets
│   │       ├── level0                  (scene/scene data)
│   │       ├── level1, level2, ...     (level bundles)
│   │       └── managed/                 (C# assemblies)
│   │           ├── Assembly-CSharp.dll  (game logic)
│   │           └── ...
│   └── ...
└── res/
    └── ...  (Android resources)
```

### 7.3 Unity Asset Extraction

```python
# Unity assets are typically:
# 1. Binary files with custom format (.assets, .unity3d)
# 2. Asset bundles (.bundle)
# 3. Sometimes serialized as JSON in newer Unity versions

# Extraction strategy:
# 1. Check if game stores data in StreamingAssets/ as JSON
#    → Easiest: just parse JSON directly
# 2. If binary: use Unity asset serializers
#    → uTinyRipper or Unity Studio
# 3. If IL2CPP: need il2cppdumper for reverse engineering
#    → Harder, may need community help

# Priority: Look for JSON first (most likely for indie Unity games)
```

---

## 8. Error Recovery Flows

```
                    ┌─────────────────┐
                    │  Capture Error  │
                    │  (no window)    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         Retry 3x       Show error       Auto-detect
         (1s delay)     in overlay       retry window
              │              │              │
              ▼              ▼              ▼
         ┌─────────────────────────┐    ┌──────────┐
         │ All retries failed?     │    │  Found   │
         └────────────┬────────────┘    │ window   │
                Yes    │         No     └────┬─────┘
                      ▼                     │
               ┌──────────────┐              │
               │ Prompt user: │              │
               │ "Start game" │              │
               └──────────────┘              ▼
                                          Resume
                                            loop

                    ┌─────────────────┐
                    │  AI Error       │
                    │  (rate limit)   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         Exponential    Show last     Fallback to
         backoff        cached resp   RAG-only view
         (1s→2s→4s→8s)  (instant)     (no AI)
              │
              ▼
         After 3 fails:
         Show "AI temporarily
         unavailable" message
```

---

*End of ARCHITECTURE.md*
