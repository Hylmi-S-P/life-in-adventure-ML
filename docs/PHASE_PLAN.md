# Phase Plan: LifeInAdventure-Tools — MVP Implementation Roadmap

> **Purpose**: Bridge between completed documentation scaffold and executable MVP.
> This plan distills exploration findings, review findings, and known risks into concrete
> phases with deliverables, gating criteria, and effort estimates.
>
> **Status**: Planning complete. Ready for Phase 0 execution.

---

## Overview

| Phase | Name | Effort | Gating | Deliverable |
|-------|------|--------|--------|-------------|
| **0** | APK Pre-Flight | 4–6 hrs | None | `EXTRACTION_REPORT.md` — confirms extraction viability |
| **1** | Core Pipeline (Vertical Slice) | 3–5 days | Phase 0 ✅ | Single end-to-end path: capture → OCR → KB match → overlay |
| **2** | Full RAG + AI Integration | 5–7 days | Phase 1 ✅ | Multi-language OCR, ChromaDB KB, AI recommendations |
| **3** | Polish & Hardening | 3–5 days | Phase 2 ✅ | Error handling, tests, config UI, edge cases |

**Total MVP estimate**: ~2–3 weeks (contiguous dev time), assuming Mono+JSON extraction path.
**If IL2CPP confirmed**: Add +1–2 weeks for community scrape pivot. See Phase 0 decision tree.

---

## Phase 0: APK Pre-Flight (4–6 hours)

### Objective

Determine game engine backend and data storage strategy **before** writing any extraction code.

### Steps

1. Download APK v1.2.42 from MuMuPlayer ADB or APKMirror
2. Decompile with `jadx`:
   ```bash
   jadx -d decoded/ life-in-adventure.apk
   ```
3. Check engine indicator:
   - `lib/armeabi-v7a/libil2cpp.so` present → **IL2CPP** (binary-encrypted quest data)
   - `assets/bin/Data/Managed/Assembly-CSharp.dll` readable → **Mono** (reflection-accessible)
   - `assets/StreamingAssets/*.json` present → **Ideal** (JSON-serialized quests)
4. Run the decision tree from `docs/data/DATA_EXTRACTION_FORENSICS.md`

### Output

`docs/data/EXTRACTION_REPORT.md` with:
- Engine backend confirmed (IL2CPP / Mono / JSON)
- Quest data population estimate (~80–1,500 expected)
- Fallback tier (T1–T4) viability
- Go/No-Go decision for pipeline approach

### Gating Criteria

| Outcome | Decision |
|---------|----------|
| Mono + JSON StreamingAssets | ✅ Proceed Phase 1 (fastest path) |
| Mono + Assembly-CSharp.dll | ✅ Proceed Phase 1 (reflection needed, +1 day) |
| IL2CPP + no JSON | ❌ **Pivot**: Community Fandom scrape fallback (Tier 4). Timeline +1–2 weeks |

### References

- `docs/data/DATA_EXTRACTION_FORENSICS.md` — Full pre-flight playbook
- `docs/review/REVIEW_REPORT.md` $C5 — IL2CPP blocker rationale

---

## Phase 1: Core Pipeline — Vertical Slice (3–5 days)

### Objective

Build ONE complete end-to-end path to validate the tech stack. Not scaffolding — real
code that produces visible output.

### Architecture (Phase 1)

```
MuMuPlayer screenshot (manual capture)
        |
        v
  ScreenCapture (mss)
        |
        v
  EasyOCR (hardcoded path)
        |
        v
  TextNormalizer (regex + dedup)
        |
        v
  ChromaDB (5 hardcoded entries)
        |
        v
  customtkinter overlay (text result)
```

### Deliverables

#### 1.1 Screen Capture Module

- **File**: `src/capture/screen_capture.py`
- **Implements**: `ScreenCapture` class
  - `capture_window()` -> PIL.Image (screenshot of MuMuPlayer)
  - `window_enum_callback()` -> find emulator window by title
  - `is_duplicate(pil_image)` -> hash-based dedup (4-frame window)
- **Depends on**: `mss`, `Pillow`, `pywin32` (Windows)
- **Effort**: ~4–6 hours

#### 1.2 OCR Engine

- **File**: `src/ocr/text_extractor.py`
- **Implements**: `OcrEngine` class
  - `extract(pil_image)` -> `OcrResult` (raw text + bounding boxes)
  - Preprocessing: grayscale -> contrast -> resize x2 (Lanczos)
  - Language: `["en"]` initially
- **Depends on**: `EasyOCR`
- **Test fixture requirement**: Save 1–3 real game screenshots to `tests/fixtures/screenshots/`
- **Effort**: ~3–5 hours (model download time ~10 min first run)

#### 1.3 Text Normalizer

- **File**: `src/ocr/text_normalizer.py`
- **Implements**: `TextNormalizer` class
  - `normalize(raw_text)` -> cleaned text (bracket fix, space fix, dedup)
  - OCR failure patterns from `docs/ocr/OCR_PERFORMANCE_BASELINE.md`
- **Effort**: ~2 hours

#### 1.4 Minimal ChromaDB Knowledge Base

- **Files**: `src/rag/knowledge_base.py`, `src/rag/embedder.py`, `src/rag/retriever.py`
- **Implements**:
  - 5 hardcoded quests/events/choices in ChromaDB
  - `similarity_search(text)` -> top-3 matches
  - `get_choices_for_event(event_id)` -> available choices
- **Depends on**: `chromadb==1.5.9`, `sentence-transformers`
- **Effort**: ~4 hours

#### 1.5 Minimal Overlay UI

- **File**: `src/ui/overlay_window.py`
- **Implements**: `OverlayWindow` class
  - Semi-transparent customtkinter window (always-on-top)
  - Text display for OCR output + matched choices
  - "Loading KB..." initial state
- **Depends on**: `customtkinter`
- **Effort**: ~3–4 hours

#### 1.6 Integration in main.py

- Wire components into existing `_init_components()` function
- Test: `python src/main.py --no-ai` (RAG-only mode)
- **Effort**: ~2 hours

### Gating Criteria

- All 6 modules implemented and importable
- At least 1 real game screenshot in `tests/fixtures/screenshots/`
- `python src/main.py --no-ai` runs without crashing
- Output text displays in overlay window
- ChromaDB returns correct matches for test queries

### References

- `SPEC.md` — Full technical spec ($7 performance, $8 error handling)
- `docs/architecture/ARCHITECTURE.md` — System deep dive ($2 pipeline, $3 data flow)
- `docs/ocr/OCR_PERFORMANCE_BASELINE.md` — OCR accuracy targets

---

## Phase 2: Full RAG + AI Integration (5–7 days)

### Objective

Replace hardcoded KB with real extraction data, add AI recommendation engine, and
implement the full pipeline with EventBus.

### Deliverables

#### 2.1 APK Extraction Pipeline

- **Files**: `src/data_extraction/apk_extractor.py`, `src/data_extraction/game_data_parser.py`
- **Implements**:
  - Download/decompile APK via jadx
  - Parse JSON StreamingAssets -> structured quest/event/choice/epilogue data
  - Validate against `docs/data/DATA_SCHEMA.md` schema
- **Pivot path** (if IL2CPP confirmed): Community Fandom scrape parser
- **Effort**: 2–3 days (JSON) / 3–5 days (community scrape)

#### 2.2 Full ChromaDB Knowledge Base

- Build KB from extracted JSON (or community scrape)
- Populate 4 collections: quests, events, choices, epilogues
- Target coverage: ~1,000–3,000 events (C4 estimate)
- Validate with sample queries against ground truth
- **Effort**: 1–2 days

#### 2.3 AI Decision Engine

- **File**: `src/ai/decision_engine.py`
- **Implements**: `AIDecisionEngine` class
  - Provider abstraction (ZCode -> OpenAI -> Ollama)
  - System prompt with EXP MANAGEMENT RULE + alignment model (C1, C2)
  - `recommend(game_state)` -> `AIRecommendation`
  - `exp_delta` and `is_exp_avoidance` in choice output (C1)
- **Depends on**: `anthropic`, `openai` SDKs
- **Effort**: 1 day

#### 2.4 EventBus Wiring

- Replace inline `_EventBusStub` with real module at `src/utils/event_bus.py`
- Wire all 6 pipeline events (ARCHITECTURE.md $1.2)
- Implement async handlers for heavy stages (OCR, AI)
- **Effort**: 4–6 hours

#### 2.5 Multilingual OCR

- Expand EasyOCR languages: `["en", "ko", "id", "es", "it", "pt"]`
- Per-language ChromaDB collections (REVIEW_REPORT L1)
- Add language detection heuristic to TextNormalizer
- **Effort**: 4–6 hours

### Gating Criteria

- All 6 pipeline stages emit/log their events
- AI recommendation appears in overlay with `exp_delta` per choice
- KB covers >= 50% of encountered quests during gameplay test
- `python src/main.py` runs full pipeline (with AI enabled)
- Fallback provider chain works (ZCode -> OpenAI -> Ollama)

### References

- `docs/api/API_CONTRACT.md` — Prompt formats, GameStateContext, ChoiceAnalysis
- `docs/data/DATA_SCHEMA.md` — Full schema with Choice.exp_cost, Alignment.from_int
- `docs/review/review_prompt_v2.md` — Patch validation checklist

---

## Phase 3: Polish & Hardening (3–5 days)

### Objective

Production-readiness: error handling, tests, config UI, edge cases, documentation
finalization.

### Deliverables

#### 3.1 Error Handling & Recovery

- Implement exception hierarchy from `SPEC.md $8.1`:
  - `APKExtractionError`, `IL2CPPNotSupportedError`
  - `OCRError`, `OCRTimeoutError`
  - `KBNotFoundError`, `RAGNoMatchError`, `RAGTimeoutError`
  - `AIProviderError`, `AIRateLimitError`, `OverlayError`
- Recovery strategies per `SPEC.md $8.2` recovery table
- **Effort**: 1 day

#### 3.2 Tests

- `tests/test_ocr_baseline.py` — OCR accuracy against ground truth fixtures
- `tests/test_rag_retrieval.py` — ChromaDB query correctness
- `tests/test_pipeline.py` — End-to-end integration (mock capture)
- `tests/test_config.py` — Config load/save round-trip, validation
- Minimum: 5 test fixtures, 10 test cases
- Run: `python -m pytest tests/`
- **Effort**: 1–2 days

#### 3.3 Config UI

- Settings panel in overlay: `src/ui/settings_panel.py`
  - Provider selection (ZCode/OpenAI/Ollama)
  - Capture interval slider (1–6s, adaptive toggle)
  - OCR language multi-select
  - Log level selector
- Wire to config hot-reload via EventBus `EVENT_CONFIG_CHANGED`
- **Effort**: 1 day

#### 3.4 Edge Cases

| Scenario | Expected Behavior |
|----------|------------------|
| No emulator running | Show setup wizard with emulator selection |
| No AI API key configured | Run in RAG-only mode with clear banner |
| Game font/UI changed | Version check + re-calibration prompt |
| High CPU/GPU contention | Adaptive capture interval (I2) |
| OCR returns empty/ garbled text | Fallback to manual text paste |
| First run (no config) | Default config + setup wizard |

- **Effort**: 1 day

#### 3.5 Documentation Finalization

- Update all doc version banners to v1.2
- Add architecture decision records (ADRs) for key choices
- Fill remaining `TODO:` markers in code comments
- Verify all cross-doc links resolve correctly
- **Effort**: 4–6 hours

### Gating Criteria

- `python -m pytest tests/` passes (>=10 tests)
- 30-minute continuous gameplay test without crash or memory leak
- All exception types defined and handled in pipeline
- Config changes take effect at runtime without restart
- Overlay works on 1920x1080 and 2560x1440 displays

### References

- `docs/metrics/METRICS_AND_OBSERVABILITY.md` — Alert thresholds, latency budgets
- `docs/security/SECURITY_PRIVACY.md` — GDPR, data handling, opt-out
- `docs/setup/SETUP_GUIDE.md` — Installation verification checklist

---

## Risk Register (Implementation Phase)

| Risk | Phase | Likelihood | Impact | Mitigation |
|------|-------|-----------|--------|------------|
| **IL2CPP confirmed** | 0 | Medium | Critical | Pivot to community scrape. Fallback documented in `DATA_EXTRACTION_FORENSICS.md` |
| **EasyOCR accuracy < 50%** | 1 | Medium | High | Tesseract fallback; custom font fine-tuning; manual text paste option |
| **ChromaDB v1.5.9 API mismatch** | 1 | Low | Medium | Pin to 0.5.23 if incompatible; migration path in requirements.txt note |
| **ZCode/Ollagon gateway down** | 2 | Low | High | Auto-fallback to OpenAI (configured); local Ollama as last resort |
| **Windows DPI/scaling breaks overlay** | 1 | Medium | Medium | Test on multiple DPI; use customtkinter scaling API; document known issues |
| **Game update changes font/layout** | 3 | Low | High | Version detection; re-calibration prompt; community alert channel |
| **Community labels tool as cheating** | 3 | Low | High | Disclaimer in overlay; educational-use-only stance; no save-file modification |

---

## Dependency Graph

```
Phase 0 (APK Pre-Flight)
    |
    v
Phase 1 (Vertical Slice)
    |-- 1.1 ScreenCapture ------|
    |-- 1.2 OCR Engine ---------|
    |-- 1.3 TextNormalizer -----|
    |-- 1.4 ChromaDB KB --------|
    |-- 1.5 Overlay UI ---------|
    |-- 1.6 Integration --------|
    |
    v
Phase 2 (Full Pipeline)
    |-- 2.1 APK Extraction -----|
    |-- 2.2 Full KB Build ------|
    |-- 2.3 AI Decision Engine -|
    |-- 2.4 EventBus Wiring ----|
    |-- 2.5 Multilingual OCR ---|
    |
    v
Phase 3 (Polish)
    |-- 3.1 Error Handling -----|
    |-- 3.2 Tests --------------|
    |-- 3.3 Config UI ----------|
    |-- 3.4 Edge Cases ---------|
    |-- 3.5 Doc Finalization ---|
```

### Parallelization Opportunities

Phases are sequential overall, but within each phase:
- **Phase 1**: 1.1 (ScreenCapture) and 1.5 (Overlay) can start in parallel
- **Phase 2**: 2.3 (AI Engine) and 2.5 (Multilingual OCR) are independent
- **Phase 3**: 3.1 (Error Handling) and 3.2 (Tests) can overlap

---

## Quick-Start Checklist

```markdown
Phase 0 — APK Pre-Flight
- [ ] Download APK v1.2.42
- [ ] Run jadx decompile
- [ ] Check for libil2cpp.so vs Assembly-CSharp.dll
- [ ] Write EXTRACTION_REPORT.md with decision

Phase 1 — Vertical Slice
- [ ] 1.1 Implement ScreenCapture
- [ ] 1.2 Implement OcrEngine + save test screenshot
- [ ] 1.3 Implement TextNormalizer
- [ ] 1.4 Implement ChromaDB KB (5 entries)
- [ ] 1.5 Implement OverlayWindow
- [ ] 1.6 Wire in main.py and test

Phase 2 — Full Pipeline
- [ ] 2.1 Build extraction pipeline / scrape parser
- [ ] 2.2 Build full KB (~1K–3K events)
- [ ] 2.3 Implement AIDecisionEngine
- [ ] 2.4 Wire EventBus
- [ ] 2.5 Add multilingual OCR

Phase 3 — Polish
- [ ] 3.1 Implement exception hierarchy + recovery
- [ ] 3.2 Write tests (>=10)
- [ ] 3.3 Build config settings panel
- [ ] 3.4 Handle all edge cases
- [ ] 3.5 Finalize docs to v1.2
```

---

## Document Cross-Reference

| Phase | Primary Documents |
|-------|-------------------|
| Phase 0 | `docs/data/DATA_EXTRACTION_FORENSICS.md`, `docs/review/REVIEW_REPORT.md` |
| Phase 1 | `SPEC.md`, `docs/architecture/ARCHITECTURE.md`, `docs/ocr/OCR_PERFORMANCE_BASELINE.md` |
| Phase 2 | `docs/api/API_CONTRACT.md`, `docs/data/DATA_SCHEMA.md`, `docs/data/GAME_MECHANICS.md` |
| Phase 3 | `docs/metrics/METRICS_AND_OBSERVABILITY.md`, `docs/security/SECURITY_PRIVACY.md` |
| All | `docs/prd/PRD.md`, `docs/setup/SETUP_GUIDE.md`, `docs/review/review_prompt_v2.md` |

---

*Created: 2026-07-07*
*Based on exploration findings, REVIEW_REPORT.md C1-C5, and ses_0cd6 full audit.*
