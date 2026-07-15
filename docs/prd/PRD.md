# Life in Adventure — AI-Powered Quest Assistant
## Product Requirements Document (PRD)

> **v1.1 (2026-07-06)**: Patches per `docs/review/REVIEW_REPORT.md`:
> - C1: EXP Fasting strategi sekarang disebut sebagai critical gameplay mechanic untuk AI reasoning
> - C4: KB count estimates diubah dari angka invent ke rentang ("~1,000-3,000 events")
> - C5: IL2CPP catastrophic blocker ditambahkan ke Risk Register
> - Risk register diperluas dari 6 ke 8 row

---

## 1. Problem Statement

**Life in Adventure** adalah text-based RPG dengan sistem pilihan kompleks. Setiap pilihan dipengaruhi oleh 6 stats (STR/DEX/INT/CHA/CON/WIS, range 1-27+), pilihan masa lalu, alignment (5 discrete tier: Good/Moral/Neutral/Impure/Evil), EXP bar (max 100 → ending triggered), dan luck (D20 dice roll + Power Points dari equipment). Pemain sering menghadapi:

- Pilihan yang hasilnya tidak jelas tanpa trial & error
- Requirement stat yang tidak terdisplay (玩家 harus nebak apakah cukup STR-nya?)
- Quest yang terasa "terputus" karena salah pilih
- Tidak ada referensi cepat untuk optimal path

Saat ini, komunitas sudah punya guide di Reddit (121+ votes) dan Scribd (74 pages), tapi **spread across multiple sources** dan **tidak real-time** dengan gameplay.

---

## 2. Vision & Goal

**Buat overlay assistant yang membuat pengalaman main Life in Adventure jadi:**
- **Less frustrating** — tau outcome sebelum pilih
- **More strategic** — AI kasih rekomendasi berdasarkan stat player
- **More informed** — quest context, loot preview, risk assessment

**MVP Goal**: Overlay panel minimal yang berfungsi sebagai "co-pilot" saat main game di MuMuPlayer emulator.

---

## 3. Target Users

- **Primary**: Pemain Life in Adventure yang mau optimalisasi pengalaman
- **Secondary**: Content creator yang mau streaming/showcase game
- **Tertiary**: Speedrunner / completionist yang mau collect semua epilogue

---

## 4. System Architecture

### 4.1 High-Level Flow

```
┌──────────────────┐       ┌─────────────────┐       ┌──────────────────┐
│  MuMuPlayer      │       │  Overlay Tool   │       │  AI Engine       │
│  (Game Running)  │──────►│  (Python App)   │──────►│  (ZCode API)     │
│                  │  cap  │  OCR + RAG      │ query │                  │
│                  │◄──────│  (Local)        │◄──────│                  │
└──────────────────┘ frame └─────────────────┘ resp  └──────────────────┘
```

### 4.2 Component Breakdown

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OVERLAY TOOL (Python)                        │
├─────────────┬─────────────┬──────────────┬──────────────┬─────────┤
│  Screen     │  OCR        │  RAG         │  AI Decision │ Overlay │
│  Capture    │  Engine     │  Retrieval   │  Engine      │ UI      │
│  (mss)      │  (EasyOCR)  │  (ChromaDB)  │  (ZCode API) │ (TUI)   │
└─────────────┴─────────────┴──────────────┴──────────────┴─────────┘
      │             │             │                │              │
      │ screenshot  │ extract     │ match quest    │ generate     │
      │ every N sec │ text+choice │ from KB        │ response     │
      │             │             │                │              │
      ▼             ▼             ▼                ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     RAG KNOWLEDGE BASE (ChromaDB)                    │
│  ┌────────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ Quest DB    │  │ Event DB   │  │ Choice DB   │  │ Outcome DB   │ │
│  │ - quest id │  │ - event id │  │ - choice id │  │ - outcomes   │ │
│  │ - title    │  │ - text     │  │ - options   │  │ - rewards    │ │
│  │ - location │  │ - type     │  │ - stat reqs │  │ - risks      │ │
│  │ - tier     │  │ - context  │  │ - success % │  │ - unlocks    │ │
│  └────────────┘  └────────────┘  └─────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. MVP Features

### 5.1 Core Features (MVP — Phase 1)

| # | Feature | Priority | Description |
|---|---------|----------|-------------|
| F1 | Screen Capture Loop | **Must Have** | Screenshot MuMuPlayer window setiap 2-3 detik |
| F2 | OCR Text Extraction | **Must Have** | Extract teks event dan pilihan dari screenshot |
| F3 | Quest Recognition | **Must Have** | Match teks dengan knowledge base → identify quest |
| F4 | Choice Outcome Display | **Must Have** | Tampilkan hasil potensial tiap pilihan, termasuk `exp_delta` per choice (C1 fix) |
| F5 | Overlay Panel UI | **Must Have** | Panel transparan di atas emulator dengan EXP bar visualization + tier milestone markers |
| F6 | AI Recommendation | **Must Have** | AI kasih saran pilihan terbaik berdasarkan stat + **EXP management** (C1 critical: support EXP Fasting strategy) |

### 5.2 Nice-to-Have (Post-MVP)

| # | Feature | Priority | Description |
|---|---------|----------|-------------|
| F7 | Player Stat Input | Should Have | Input stat player → AI lebih akurat |
| F8 | Quest Progress Tracker | Should Have | Track quest yang sudah selesai |
| F9 | Multiple Ending Tracker | Should Have | Show which endings player has unlocked |
| F10 | Alert/Notification Mode | Could Have | Notifikasi saat quest penting muncul |

---

## 6. Data Architecture

### 6.1 APK Data Extraction Pipeline

```
[APK File] → [jadx decompile] → [Unity asset extraction]
                                        │
                                        ▼
                              [Raw Game Data Files]
                                        │
                                        ▼
                              [Parser Script]
                                        │
                                        ▼
                              [Structured JSON]
                                        │
                                        ▼
                              [ChromaDB Knowledge Base]
                                        │
                                        ▼
                              [Embedding + Vector Store]
```

### 6.2 Update Strategy

- **Extraction trigger**: Manual — user jalankan script saat versi baru terinstall
- **Diff approach**: Re-extract full → compare dengan backup → hanya update yang berubah
- **Community fallback**: Kalau APK extraction gagal, rely pada community data (Reddit guide, Fandom wiki)

### 6.3 Knowledge Base Schema

```json
{
  "quest": {
    "id": "q_main_001",
    "title": "Haunted Manor",
    "type": "side_quest",
    "location": "Town",
    "description": "Help the priest investigate a haunted manor",
    "requirements": { "min_level": 3 },
    "events": ["evt_manor_01", "evt_manor_02"],
    "outcomes": {
      "success": ["epilogue_haunted_01"],
      "partial": ["epilogue_haunted_02"],
      "fail": ["epilogue_haunted_03"]
    }
  },
  "event": {
    "id": "evt_manor_01",
    "quest_id": "q_main_001",
    "text": "The manor looms before you...",
    "choices": [
      {
        "id": "ch_manor_01_a",
        "text": "Enter through the front door",
        "stat_check": { "stat": "DEX", "threshold": 5, "description": "Sneak past the guard" },
        "outcomes": [
          { "condition": "success", "result": "You enter undetected...", "reward": null },
          { "condition": "fail", "result": "The guard spots you!", "risk": "Combat encounter" }
        ]
      },
      {
        "id": "ch_manor_01_b",
        "text": "Knock on the door",
        "stat_check": { "stat": "CHA", "threshold": 6, "description": "Charm your way in" },
        "outcomes": [...]
      }
    ]
  },
  "epilogue": {
    "id": "epilogue_haunted_01",
    "name": "Ghost Hunter",
    "description": "You cleared the manor of spirits",
    "requirements": [...],
    "rewards": { "gold": 200, "items": ["Holy Water"], "stat_bonus": null }
  },
  "background": {
    "id": "bg_adventurer",
    "name": "Adventurer's Dream",
    "stat_modifier": { "STR": +1 },
    "starting_items": ["Rusty Sword"],
    "affects_quests": ["q_main_*"]
  }
}
```

---

## 7. User Experience

### 7.1 Workflow

```
1. User jalankan MuMuPlayer → buka Life in Adventure
2. User jalankan overlay tool → tool auto-detect MuMuPlayer window
3. Tool mulai capture loop → setiap 3 detik screenshot + OCR
4. Kalau teks quest baru terdeteksi → RAG query → tampilkan info
5. User baca overlay → pertimbangkan pilihan → pilih di game
6. Repeat sampai quest selesai
```

### 7.2 Overlay UI Mockup (MVP)

```
╔══════════════════════════════════════════════════════════════╗
║ 🎮 Life in Adventure — Quest Assistant                   [—]║
╠══════════════════════════════════════════════════════════════╣
║                                                               ║
║  📖 QUEST: The Haunted Manor                              ██░║
║  ─────────────────────────────────────────────────────────────║
║  Help the priest investigate strange occurrences at the      ║
║  old manor on the hill.                                      ║
║                                                               ║
║  ┌─ AVAILABLE CHOICES ────────────────────────────────────┐  ║
║  │                                                          │  ║
║  │  [A] Enter through the front door                        │  ║
║  │      ⚡ DEX check (5+) — Sneak past the guard            │  ║
║  │      ✅ Success: Enter undetected, skip combat            │  ║
║  │      ❌ Fail: Trigger combat with guard                   │  ║
║  │                                                          │  ║
║  │  [B] Knock on the door                                   │  ║
║  │      ⚡ CHA check (6+) — Charm your way in              │  ║
║  │      ✅ Success: Get inside, possible ally inside       │  ║
║  │      ❌ Fail: Door stays shut, wastes 1 turn             │  ║
║  │                                                          │  ║
║  │  [C] Look for another entrance                           │  ║
║  │      📦 No stat check — Safe but may miss loot          │  ║
║  │      ✅ Success: Find secret passage                     │  ║
║  │      ⚠️  Neutral: No reward, no risk                     │  ║
║  │                                                          │  ║
║  └──────────────────────────────────────────────────────────┘  ║
║                                                               ║
║  ┌─ AI RECOMMENDATION ────────────────────────────────────┐  ║
║  │                                                          │  ║
║  │  🏆 Best: [B] if CHA ≥ 6 — Best outcome, ally bonus      │  ║
║  │  🥈 Safe: [A] if DEX ≥ 5 — Fast, combat possible        │  ║
║  │  🟡 Neutral: [C] — Guaranteed entry, no bonus           │  ║
║  │                                                          │  ║
║  │  💡 Tip: If you have Fiana companion, [A] is safest     │  ║
║  │                                                          │  ║
║  └──────────────────────────────────────────────────────────┘  ║
║                                                               ║
║  ─────────────────────────────────────────────────────────────║
║  ⚙️ Stats: STR:8 DEX:6 INT:5 CHA:4 CON:7 WIS:5  │ KB: v1.2.42 ║
╚══════════════════════════════════════════════════════════════╝
```

### 7.3 Configuration Panel

```
╌─ Settings ─────────────────────────────────────────────────────┐
│  📺 Emulator: [MuMuPlayer ▼]     [🔍 Detect]                  │
│  📷 Capture Interval: [3] seconds                              │
│  🎯 Overlay Position: [Right side ▼]   [Custom: x,y ]        │
│  🤖 AI Model: [ZCode/Claude ▼]                                │
│  📊 AI Verbosity: [Brief ▼]  (Brief / Detailed / Expert)    │
│  🗣️ Language: [English ▼]                                      │
│  🔄 Auto-start capture: [✓]                                    │
│  🎨 Theme: [Dark ▼]  (Dark / Light / AMOLED)                  │
│                                                                │
│  📂 Knowledge Base: C:\...\lia_kb_v1.2.42                     │
│  └─ Status: ✅ Loaded (2,341 quests, 8,920 events)            │
│                                                                │
│  ⌨️ Hotkeys:                                                   │
│  └─ Pause/Resume: [F9]   Refresh KB: [F10]   Quit: [F12]     │
└────────────────────────────────────────────────────────────────┘
```

---

## 8. Technical Specifications

### 8.1 Tech Stack

| Layer | Technology | Justification |
|-------|------------|---------------|
| **Language** | Python 3.11+ | OCR, data processing, RAG — ecosystem mature |
| **Screen Capture** | `mss` | Fast, cross-platform, low CPU |
| **OCR** | `EasyOCR` | Handles game pixel art font lebih baik dari Tesseract |
| **RAG Store** | `ChromaDB` | Local-first, zero-config, Python-native |
| **Embedding** | `sentence-transformers` (`all-MiniLM-L6-v2`) | Fast, good quality, CPU-capable |
| **AI Engine** | ZCode API (`gateway.olagon.site`) | Already configured, Claude-powered via Ollagon gateway |
| **UI/Overlay** | `customtkinter` atau `PyQt6` | Native-feel overlay, transparent window |
| **APK Decompile** | `jadx` | Best Java decompiler untuk Unity/Java apps |
| **Data Parse** | Custom Python scripts | Parse Unity JSON/text bundles |

### 8.2 File Structure

```
D:/LifeInAdventure-Tools/
├── docs/
│   └── prd/
│       └── PRD.md
├── src/
│   ├── __init__.py
│   ├── main.py                    # Entry point
│   ├── config.py                  # Config loader
│   ├── capture/
│   │   ├── __init__.py
│   │   ├── screen_capture.py     # Screenshot loop
│   │   └── emulator_detector.py   # Auto-detect MuMuPlayer
│   ├── ocr/
│   │   ├── __init__.py
│   │   ├── text_extractor.py     # OCR processing
│   │   └── text_normalizer.py    # Clean up OCR noise
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── knowledge_base.py     # ChromaDB interface
│   │   ├── embedder.py           # Sentence transformer
│   │   └── retriever.py          # RAG retrieval logic
│   ├── ai/
│   │   ├── __init__.py
│   │   └── decision_engine.py    # ZCode API wrapper
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── overlay_window.py     # Main overlay
│   │   └── settings_panel.py      # Config UI
│   └── data_extraction/
│       ├── __init__.py
│       ├── apk_extractor.py       # APK download + decompile
│       └── game_data_parser.py   # Parse game assets
├── data/
│   ├── knowledge_base/            # ChromaDB persist
│   │   ├── chroma.sqlite
│   │   └── ...
│   ├── raw_extracted/            # Raw APK data (v1.2.x)
│   └── parsed/                   # Structured JSON
├── scripts/
│   ├── setup_env.py               # Install dependencies
│   ├── first_time_setup.py        # Initial KB build
│   └── extract_apk.py             # APK extraction script
├── configs/
│   └── default_config.yaml        # Default settings
├── tests/
│   ├── test_ocr.py
│   ├── test_rag.py
│   ├── test_ai.py
│   └── test_integration.py
├── README.md
├── requirements.txt
├── SPEC.md
└── .gitignore
```

### 8.3 API Contract — ZCode AI Engine

```python
# src/ai/decision_engine.py

SYSTEM_PROMPT = """You are an expert Life in Adventure game assistant.
You have access to a RAG knowledge base with quest data, choice outcomes,
and epilogue requirements.

For each query:
1. Identify the quest and its context
2. Analyze each available choice with its stat requirements
3. Predict outcomes based on player's current stats
4. Recommend the best choice with reasoning
5. Warn about risks and alternative paths

Be concise in MVP. Use bullet points. Highlight stat checks clearly."""

def get_recommendation(
    quest_text: str,
    choices: list[str],
    player_stats: dict[str, int] | None,  # STR, DEX, INT, CHA, CON, WIS
    knowledge_context: str  # Retrieved from RAG
) -> str:
    """
    Returns AI-generated recommendation for current game state.
    """
```

### 8.4 Performance Requirements

| Metric | Target | Notes |
|--------|--------|-------|
| **Screenshot → OCR** | < 1.5s | Per frame |
| **OCR → RAG query** | < 500ms | Retrieval |
| **RAG → AI response** | < 3s | ZCode API latency |
| **Total latency** | < 5s end-to-end | Acceptable for gameplay |
| **Memory usage** | < 500MB | Desktop/laptop acceptable |
| **CPU usage** | < 30% | Idle between captures |

---

## 9. Development Phases

### Phase 1 — MVP (Target: 3–5 weeks; see `docs/PHASE_PLAN.md` for detailed breakdown)
- [ ] Setup environment (Python, dependencies)
- [ ] APK data extraction (v1.2.42)
- [ ] Build ChromaDB knowledge base
- [ ] Screen capture + OCR pipeline
- [ ] RAG retrieval (quest recognition)
- [ ] Basic overlay UI
- [ ] AI recommendation integration
- [ ] End-to-end test with MuMuPlayer

### Phase 2 — Polish (Target: 1 week)
- [ ] Settings/config panel
- [ ] Emulator auto-detection
- [ ] Multiple emulator support
- [ ] KB update script (version diffing)
- [ ] Player stat input

### Phase 3 — Community (Post-MVP)
- [ ] Community data contribution pipeline
- [ ] KB sharing/distribution
- [ ] Multi-language support (EN/KR/ID sudah ada di game)

---

## 10. Risks & Mitigations

> ⚠️ **Updated per C5 (REVIEW_REPORT)**: IL2CPP catastrophic blocker must be detected pre-flight before Phase 1 begins. See `docs/data/DATA_EXTRACTION_FORENSICS.md` for pre-flight check.

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OCR fails on game font | Medium | High | Use EasyOCR + custom font training; fallback to manual text paste |
| APK data encrypted | Low | High | Investigate Unity asset encryption; community fallback |
| **APK uses IL2CPP backend** (NEW per C5) | **Medium** | **CRITICAL** | **Pre-flight check via `DATA_EXTRACTION_FORENSICS.md`. If confirmed, MVP pivots to community Fandom scrape fallback. Timeline +1-2 weeks.** |
| **APK extraction reads JSON but schema unknown** (NEW per C5) | **High** | Medium | `infer_schema` per `GameDataParser` (SPEC §3.6); manual mapping post-extraction |
| Overlay blocking game | Medium | Medium | Always-on-top but semi-transparent; resizable/draggable |
| AI response too slow | Low | Medium | Cache frequent queries; show "thinking..." state |
| Game update breaks KB | Low | Low | Version check; prompt user to re-extract |
| ZCode API rate limit | Low | Low | Rate limiting; local cache of frequent queries |
| **Game patch changes OCR font/layout** (NEW) | Low (6-mo cycle) | High | Re-calibrate OCR fixtures post-patch; community alert channel |
| **Community labels tool as cheating → DMCA** (NEW) | Low | High | Disclaimer: educational use, no automation/bot, no save modification, no commercial use |

---

## 11. Success Metrics (MVP)

- ✅ Tool berhasil recognize minimal **50% quest** yang muncul di gameplay
- ✅ AI recommendation muncul dalam **< 5 detik** setelah OCR selesai (p99, see `docs/metrics/METRICS_AND_OBSERVABILITY.md`)
- ✅ Overlay tidak crash selama **30 menit** gameplay continuous
- ✅ User bisa main game dengan overlay tanpa friction signifikan
- ✅ Knowledge base cover minimal: semua **main quest + 20 side quest** (note C4: actual counts may be 1,000-3,000 events — see `docs/data/DATA_SCHEMA.md` §1)
- ✅ **NEW (C1)**: EXP management rule aktif — tool menampilkan warning saat `current_exp > 80` dan target epilogue belum unlocked
- ✅ **NEW (C1)**: Setiap choice analysis di output termasuk `exp_delta` field

---

## 12. Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Apakah data game di APK plain-text atau encrypted? | 🔍 To be verified (APK extraction) |
| Q2 | Apakah Unity build-nya mono/.NET atau IL2CPP? | 🔍 To be verified |
| Q3 | Bagaimana alignment system mempengaruhi outcomes? | 🔍 Need community input |
| Q4 | Apakah player save file readable/parseable? | 🔍 To be explored |
| Q5 | Apakah Discord community mau collaborate di KB? | 🔍 To be asked after MVP |

---

*Document version: 1.0*
*Created: 2026-07-05*
*Author: AI-assisted, Lenix*
