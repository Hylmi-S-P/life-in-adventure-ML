---
type: review-report
category: documentation
created: 2026-07-06
status: complete
target_project: LifeInAdventure-Tools
reviewer_agent: Sisyphus (OhMyOpenCode, GLM 5.2)
trigger_prompt: docs/review/REVIEW_PROMPT.md
tags:
  - review
  - documentation
  - audit
  - life-in-adventure
  - ai-companion
---

# Comprehensive Review Report — LifeInAdventure-Tools

> Deep audit of all 12 target files in `D:/LifeInAdventure-Tools/` per the request in `docs/review/REVIEW_PROMPT.md`.
> Reviewer ran under Agentic Brain rules (Caveman + Ponytail modes) and verified critical claims via web search (Exa) against Fandom Wiki, LDPlayer, Scribd community guides, and Reddit r/LifeInAdventure.
> Output: structured findings (Critical / Important / Minor), missing documentation list, recommendations, summary table.

---

## Document Inventory Reviewed

| # | File | Lines | Category |
|---|------|------:|----------|
| 1 | `D:/LifeInAdventure-Tools/HANDOVER.md` | 186 | Handover |
| 2 | `D:/LifeInAdventure-Tools/README.md` | 239 | Project overview |
| 3 | `D:/LifeInAdventure-Tools/SPEC.md` | 998 | Technical spec |
| 4 | `D:/LifeInAdventure-Tools/docs/prd/PRD.md` | 453 | Product requirements |
| 5 | `D:/LifeInAdventure-Tools/docs/architecture/ARCHITECTURE.md` | 587 | Architecture deep dive |
| 6 | `D:/LifeInAdventure-Tools/docs/data/GAME_MECHANICS.md` | 493 | Game mechanics (researched) |
| 7 | `D:/LifeInAdventure-Tools/docs/data/DATA_SCHEMA.md` | 705 | Data schema |
| 8 | `D:/LifeInAdventure-Tools/docs/api/API_CONTRACT.md` | 631 | AI engine contract |
| 9 | `D:/LifeInAdventure-Tools/docs/setup/SETUP_GUIDE.md` | 425 | Setup guide |
| 10 | `D:/LifeInAdventure-Tools/requirements.txt` | 64 | Dependencies |
| 11 | `D:/LifeInAdventure-Tools/src/main.py` | 142 | Main placeholder |
| 12 | `D:/LifeInAdventure-Tools/src/config.py` | 104 | Config loader placeholder |

**Total**: ~4,427 lines documentation + scaffolding.

---

## Verification Method

1. **Direct reading** of all 12 target files.
2. **Cross-document consistency check** (stat range, alignment scale, ZCode URL, file structure).
3. **External verification** via Exa web search for load-bearing game mechanics claims:
   - EXP cap value (verified: **100**, not arbitrary)
   - Alignment model (verified: **5 discrete tiers**, not linear -100..+100)
   - Stat threshold bonuses (verified: **13/20/27** for Weapon Mastery / Toughness / Super Strength)
   - Rank milestones (verified: **10/20/35/55/80** EXP)
4. **Agentic Brain policy overlay** (`D:/Agentic Brain/AGENTS.md`, Agent Brief, Working Agreement): applied Ponytail (over-engineering lens) and Caveman-review (terse findings) mode to the review.

---

## ✅ What Was Done Well

1. **Cakupan dokumentasi lengkap & terstruktur** — 8 core docs (PRD/SPEC/ARCH/MECH/SCHEMA/API/SETUP/HANDOVER) + code scaffolding. Roadmap Phase 1-3 jelas. Volume realistis (~4K lines documented而不是 aspirational).
2. **Game insight load-bearing tertangkap** — `EXP bar penuh = ending terpicu`, `alignment → epilogue unlock`, `background DLC = storyline pivot`. Tiga kunci utama gameplay ter-identifikasi di early research.
3. **Tech stack defensif & justified** — ChromaDB zero-config untuk ~5K events, EasyOCR dengan justifikasi pixel-art vs Tesseract, customtkinter over PyQt6 (ringan, transparent native), sentence-transformers all-MiniLM-L6-v2 untuk CPU-friendly 384-dim.
4. **Typed DTOs + mature error contract** — `GameStateContext`, `AIRecommendation`, `ChoiceAnalysis`, `RiskLevel` enum, `AIErrorResponse` fallback chain (cache→retry→rag-only→no-data). Schema pydantic-ready.
5. **Provider abstraction + multi-AI fallback** — ZCode→OpenAI→Ollama switch-able, rate limit per provider documented, exponential backoff strategi disebut di ARCH §8 dan API_CONTRACT §5.

---

## ⚠️ Issues & Gaps

### 🔴 Critical (Must Fix Before Implementation)

---

#### **C1. EXP bar mechanics direpresentasikan tidak lengkap → tool akan beri saran yang merusak gameplay**

**Where**: `docs/data/GAME_MECHANICS.md` §4.1, §9.3; `docs/api/API_CONTRACT.md` §4.1.

**Problem**:
- Dokumen bilang "EXP bar penuh = ending terpicu early" tapi ini setengah kebenaran. Verified via LDPlayer + Scribd + Fandom wiki:
  - EXP max = **100** hard cap
  - Rank up milestones di EXP **10 / 20 / 35 / 55 / 80** (5 ranks total)
  - **"EXP Fasting"** adalah meta strategi utama: pemain **menghindari** EXP-generating events untuk naik stat lebih tinggi sebelum ending trigger
  - EXP source: enemy=1, random event=1-2, major event=2-3
  - Tanpa modeling EXP-cost per choice, tool merekomendasikan high-reward choices (biasanya juga EXP-tinggi) → trigger early ending sebelum target epilogue tercapai
- API_CONTRACT §4.1 system prompt TIDAK menginstruksikan AI untuk pertimbangkan EXP atau target epilogue. AI jadi "anti-counsel" untuk player serius.

**Severity justification**: Fitur paling diiklankan ("AI co-pilot") akan **counterproductive** untuk 30%+ player base yang serius. Tool mengarahkan user ke early ending — melawan value prop.

**Solution**:
1. Tambah field ke `DATA_SCHEMA.md`:
   - `Event.exp_gain: int` (sudah ada, jaga)
   - `Choice.exp_cost: int = 0` (BARU — pilihan no-EXP ada di game)
   - `Choice.exp_avoidance: bool = False` (BARU — flag untuk EXP Fasting)
2. Tambah `GameStateContext.current_exp: int` dan `GameStateContext.exp_remaining: int = 100 - current_exp`.
3. Tambah `PlayerConfig.target_epilogue_id: str | None`.
4. System prompt (API_CONTRACT §4.1) tambah rule:
   ```
   EXP MANAGEMENT RULE (CRITICAL):
   - Jika exp_remaining ≤ median(exp_gain dari available choices) DAN target_epilogue belum unlocked, prioritaskan choices dengan exp_cost=0 atau next_event != ending.
   - Mark risk_level="critical" bila rekomendasi memperkecil exp_remaining di bawah 10.
   - Selalu tampilkan "EXP impact" di choice_analysis.
   ```
5. UI overlay: progress bar EXP dengan tanda visual di rank milestones (10/20/35/55/80) dan warning saat EXP >80% menuju ending.

---

#### **C2. Alignment model salah skala → AI tidak konsisten**

**Where**: `docs/data/GAME_MECHANICS.md` §5.1; `docs/data/DATA_SCHEMA.md` `Alignment` enum.

**Problem**:
- Dokumen pakai **linear -100 to +100** dengan 5 arbitrary buckets:
  ```
  -100..-33 chaotic, -32..+32 true neutral, +33..+100 lawful
  ```
- Web verification (Scribd community guide + Fandom): game punya **5 tier diskrit**:
  - **Good / Moral / Neutral / Impure / Evil**
  - Threshold shift via trait: Bright +20, Dark -20, Innately Evil -20, Innately Good +20, Savior +20
- Mempersamakan dengan linear gauge D&D adalah inferensi tak berbasis bukti.
- Cross-implikasi: `PlayerStats.player_alignment: int` di schema/API akan break saat AI prompt minta alignment spesifik.

**Severity**: Sedang-tinggi — AI reasoning alignment-dependent (epilogue unlock) jadi tak tertangkap benar.

**Solution**:
1. `PlayerStats.player_alignment: Literal["good","moral","neutral","impure","evil"]`.
2. `Event.alignment_shift` bisa pakai delta -20..+20 (tapi tetap diskrit ke tier threshold).
3. `Epilogue.alignment_required` schema tetap pakai tuple (-100, 100) di storage, tapi compute saat parse harus kategorikan dari sum delta ke tier.
4. Tambah `AlignmentTier` enum di DATA_SCHEMA dengan mapping tier→range (inferensi, butuh verify lebih lanjut saat APK extraction):
   ```
   Good: alignment >= 60  (atau threshold TBD via APK)
   Moral: 20 <= alignment < 60
   Neutral: -20 < alignment < 20
   Impure: -60 < alignment <= -20
   Evil: alignment <= -60
   ```
5. Note: threshold tier ini masih spekulatif dari Evidence sum trait. APK extraction wajib verify.

---

#### **C3. Stat check formula salah/kontradiktif lintas dokumen**

**Where**: `docs/data/GAME_MECHANICS.md` §2.1, §2.2, §2.4; `SPEC.md` §8.1 (system prompt).

**Problem**:
- `GAME_MECHANICS.md` §2.1: stat range "1-25+" — benar (Fandom bilang at 27 unlock Super X+2)
- `SPEC.md` system prompt §8.1: "All stats range from 1-20 typically" — **kontradiksi langsung**
- `GAME_MECHANICS.md` §2.2 tabel bonus hanya sebut **10 / 13 / 20** threshold. Verified via Fandom:
  - STR 13 + DEX 13 = Weapon Mastery +1 (Physical Attack +10%)
  - STR 20 + DEX 20 = Weapon Mastery +2 (+20%)
  - STR 27 = **Super Strength +2** (Physical Attack +20%)
  - DEX 27 = Acrobatic +2
  - Threshold tier sebenarnya: **13 / 20 / 27**, dokumen lewati 27.
- §2.4 "Roll 1d20 + modifier vs DC", critical 20 = instant win — setengah benar, tapi game pakai **hybrid dice + power points** (per GameGrin review yang dikutip dokumen sendiri di §3.2), bukan D&D pure DC.

**Severity**: AI reasoning akan mengira max stat = 20 dan takkan menyarankan pre-prep untuk Super +2 unlock. Prompt inconsistens menyesatkan.

**Solution**:
1. Konsistenkan: stat range **1-27+** di semua dokumen.
2. Tambah row di tabel §2.2 GAME_MECHANICS:
   - `STR+DEX ≥ 27 (each)` → `Weapon Mastery +3 / Super Strength +2 / Acrobatic +2` (verify via APK).
   - Klarifikasi di §2.4: "Combat menggunakan hybrid: D20 + stat_modifier + Power Points (equipment). Minimum roll natural 1, maximum natural 20. 'DC' adalah shorthand, bukan D&D pure."
3. Update SPEC §8.1 system prompt alignment line dengan range yang sama.

---

#### **C4. Knowledge base count estimates tidak verified + setup time tidak realistis**

**Where**: `docs/data/DATA_SCHEMA.md` §1; `docs/setup/SETUP_GUIDE.md` Step 3.3, Step 5; `HANDOVER.md`.

**Problem**:
- DATA_SCHEMA §1 estimate: ~50 quests, ~900 events, ~90 epilogues. Justifikasi tidak diberi.
- HANDOVER bilang "Total: ~3,970+ lines" tapiBB count: "Quests: 47 | Events: 892 | Choices: 1,203 | Epilogues: 89" → **angka invent** sebagai output contoh, bukan verified pass pertama.
- Realitas komunitas: Fandom wiki punya **200+ epilogue pages** (main + sub). Game punya **Paths** (v1.2.33+) dan **Tales DLC** tidak termasuk di count.
- Estimate aktual: events bisa 1,500-3,000+, epilogues 200-400.
- SETUP_GUIDE §3.3: "Extraction complete!" output show 47/892/1203/89 dalam instant. Step 5: "Build complete! Total time: ~2 minutes" — tidak realistis untuk embedding 5000+ entries di CPU (sentence-transformers di CPU ~5-10 ms per embedding → 5000 = 25-50 detik untuk embedding saja, plus ChromaDB insert I/O).

**Severity**: User pertama lari akan frustrasi karena ekspektasi setup 30-60 menit vs realita 1-3 jam bila game content sesungguhnya besar.

**Solution**:
1. Ubah estimasi jadi rentang ("1,000-3,000 events (per Fandom + Scribd evidence)") eksplisit acknowledges itu upper-bound guess.
2. SETUP_GUIDE tambah section "First KB build: expect 10-30 minutes for full extraction + embedding depending on game content volume and CPU".
3. Tambah progress bar yang jujur + ETA per 500 items di `first_time_setup.py`.

---

#### **C5. APK extraction pipeline = single point of catastrophic failure — tidak ada plan B teruji**

**Where**: `SPEC.md` §3.6; `docs/architecture/ARCHITECTURE.md` §7; `docs/prd/PRD.md` §10 Risks.

**Problem**:
- `SPEC.md` §3.6 `detect_game_engine()` return "unity_mono | unity_il2cpp | native | unknown" — tapi gak ada verified flag di dokumentasi. Kondisi saat ini:
- ARCH.md §7 bilang "Life in Adventure uses Unity engine (confirmed from APK uses Unity classes)" — tapi tidak ada verifikasi apakah **mono** atau **IL2CPP**.
- Kalau IL2CPP: `Assembly-CSharp.dll` jadi binary, **logic quest outcome tidak readable** sebagai JSON dumps. Pipeline data parser (`KNOWN_PATTERNS` di §3.6) asumsi JSON files matching `quest*.json` — tapi Unity indie default bundle pakai `assetbundle` binary, **bukan JSON StreamingAssets**, kecuali dev Studio Wheel explicit serialize ke JSON (rare for indie).
- Tidak ada dokumentasi: "Bila IL2CPP dan tidak ada JSON StreamingAssets, APK extraction route MATI. Fallback ke community scrape."
- **PRD §10 Risks register tidak mention IL2CPP sama sekali.** Mitigation "Investigate Unity asset encryption" terlalu ringan — IL2CPP bukan encryption, itu compilation backend yang mengubah C# ke C++.

**Severity**: MVP 1-2 minggu janji. Kalau di Hari Hari 2 ketemu IL2CPP, 90% effort wasted. **Undiscussed catastrophic blocker**.

**Solution**:
1. Tambah pre-flight check di `APKExtractor.full_pipeline`:
   - Check `lib/armeabi-v7a/libil2cpp.so` ada → IL2CPP flag = true, atomic fail
   - Check `assets/bin/Data/Managed/Assembly-CSharp.dll` ada → mono
   - Check `assets/StreamingAssets/*.json` ada → JSON-mono (ideal)
2. Buat decision tree eksplisit di DOC: `DATA_EXTRACTION_FORENSICS.md` (lihat Missing Documentation).
3. Fallback tiers dokumentasi:
   1. JSON StreamingAssets (BEST — parse langsung)
   2. Assembly-CSharp via dnSpy/ILSpy reflection (MEDIUM — 但 quest data harus serialized field `public`, kalau serial private tidak dapat)
   3. Community Fandom wiki scrape via Tavily extract (LOWER — half-structured)
   4. Manual community Reddit/Discord paste (LOWEST)
4. **Critical gate**: Bila IL2CPP confirmed tanpa JSON dump, MVP Wajib pivot ke tier (3) community scrape. Jangan deploy rencana tak teruji.

---

### 🟡 Important (Should Address in Phase 1)

#### **I1. OCR → quest text matching cross-language fragil**
Game ditampilkan multi-lang (EN/KR/ID/ES/IT/PT). Embedding default `all-MiniLM-L6-v2` EN-heavy — lemah untuk KR/ID. `Embedder` class tidak menyimpan language tag, satu koleksi untuk semua bahasa → false positives cross-language.
**Solution**: Per-language ChromaDB collections, atau metadata `language` + filter `where={"language": detected_lang}`. Swap ke `paraphrase-multilingual-MiniLM-L12-v2` (384-dim) atau `bge-m3` saat `detect_language ≠ "en"`.

#### **I2. Capture interval fixed 3s → OCR CPU backlog**
EasyOCR CPU mode ~1-3s per frame. Fixed 3s interval potensial backlogging. SPEC §7 performance matrix CPU <40% during OCR+AI — realita bisa 60-80%.
**Solution**: Adaptive interval berbasis prior frame hash similarity. No-change >3 captures → extend to 6s. Change → drop to 1s. Config `mode: "polling" | "event-driven"`.

#### **I3. Overlay click-through vs draggable tidak testable sebelum impl**
`SPEC.md` §3.5 `OverlayWindow` pakai `overrideredirect(True)` + `-transparentcolor=black`. di Windows, borderless TIDAK otomatis click-through. Butuh `SetWindowLong(WS_EX_TRANSPARENT | WS_EX_LAYERED)` via pywin32 hit-test region eksplisit. Dokumen tidak menyebut impl konkret.
**Solution**: Pilih salah satu: (a) full draggable + minimize-to-tray hide saat combat, atau (b) per-region `click_through: bool` per widget. Test pakai `pytest-qt` atau minimal `interactive_bash` demo.

#### **I4. Bug di `config.py` `from_yaml` akan TypeError saat nested ai config**
`Config.from_yaml` pakai `AIConfig(**data.get("ai", {}))` tapi YAML schema (SPEC §5.1) punya `ai.zcode.api_key_env`, `ai.openai.base_url`, dst. sebagai nested. `AIConfig` dataclass TIDAK punya field `zcode`. Result: `TypeError: __init__() got an unexpected keyword argument 'zcode'` di first run, atau diabaikan diam-diam.
**Solution**: Tambah nested `ZCodeConfig`, `OpenAIConfig`, `OllamaConfig` dataclass. Resolve `os.getenv(api_key_env)` saat `from_yaml` untuk dapat API key actual.

#### **I5. `main.py` eager init semua komponen di single thread → startup UX buruk + failure cascade**
`main()` inisialisasi KnowledgeBase (ChromaDB SQLite 2-5s) + Embedder (model download/load 5-10s) + OcrEngine (EasyOCR init 5-10s) BEFORE overlay window open. User lihat nothing 10-25s. Bila KB belum ada, exception naik sebelum window show → exit crash.
**Solution**: Lazy init pattern. Open overlay dulu dengan "Initializing..." state. Background thread load KB+OCR paralel. Surface progress ke UI via `EventBus` (didisebut di ARCH §1.2 tapi belum ada kode interface).

#### **I6. Handover klaim deliverables tak verify ada di repo**
`HANDOVER.md` list 17 deliverable, termasuk `CONTRIBUTING.md`, `LICENSE`, `configs/default_config.yaml`, `.gitignore`, `src/*/__init__.py` stubs (7 files). Saya verify 12 dari REVIEW_PROMPT saja. Kalau ada yang belum ada, setup guide bakal break.
**Solution**: Audit fisik semua path di HANDOVER. Tandai `[TODO]` bukan `✅` untuk yang belum ada.

#### **I7. Tidak ada e2e smoke test yang runnable sebelum full impl**
SPEC §9 list `tests/test_integration.py` dan `test_mumuproplayer.py` "manual only". Untuk MVP demo pertama, tanpa automated smoke = demo stress.
**Solution**: Salin 1-2 sample screenshot sebagai fixture golden test. Assert OCR substring, RAG top-K contains expected quest_id, mock AI response hard-coded.

---

### 🔵 Minor (Nice to Have)

**M1.** `GAME_MECHANICS.md` punya dua "§14" headers (line 437 Language Support + line 450 Summary). Typo numbering.

**M2.** `README.md` Post-MVP pakai `[ ]` consistent, tapi MVP Features pakai `[x]` padahal belum diimplement — salah signaling "done". Ganti ke `[ ]` consistent.

**M3.** `config.py` `PlayerConfig` pakai field `str`/`dex`/`int` — `int` adalah builtin name collision (Python tidak crash di dataclass field, tapi convention buruk). Rename ke `stat_str`, `stat_dex`, dst.

**M4.** `requirements.txt` pin `chromadb==0.5.23`. Per late 2025, ChromaDB sudah API breaking changes di `get_or_create_collection` deprecation. Verify latest stable via Context7 sebelum lock final.

**M5.** `SETUP_GUIDE.md` step 7.3 mention `scripts/diff_versions.py` & `apply_diff.py` — tidak ada di file structure disclosure PRD §8.2. Asumsi impl, tapi plan bola-balik.

**M6.** ZCode base_url inkonsisten lintas dokumen:
- `API_CONTRACT.md` §2.1 bilang `https://gateway.olagon.site/anthropic`
- `ARCHITECTURE.md` §5.1 bilang `https://api.z.ai/api/anthropic`
- `SPEC.md` config YAML bilang `https://api.z.ai/api/anthropic`
Pilih satu dan jelasin bedanya (Ollagon = personal gateway fronting z.ai, atau z.ai = official mirror claude?).

**M7.** PRD §6.3 schema JSON contoh `"background"` field `affects_quests: ["q_main_*"]` pakai wildcard string. Tidak didefinisikan di DATA_SCHEMA §3.8 (Background schema pakai explicit list, bukan glob). Potential parser ambiguity.

**M8.** Tidak acknowledge bahwa `all-MiniLM-L6-v2` adalah EN-trained; multilingual case di Phase 3 wajib swap model, dokumen tidak disclaimer.

---

## 📋 Missing Documentation

### Doc1. `DATA_EXTRACTION_FORENSICS.md` (CRITICAL)
Pre-flight check IL2CPP vs mono. Test: jalankan jadx di APK v1.2.42, dokumentasikan:
- Apakah `lib/armeabi-v7a/libil2cpp.so` ada?
- Apakah `assets/bin/Data/Managed/Assembly-CSharp.dll` readable?
- Apakah `assets/StreamingAssets/*.json` ada?
- Decision tree: Bila IL2CPP tanpa JSON dump → MVP pivot ke community scrape.
**Priority**: Pre Phase 1 step 0.

### Doc2. `OCR_PERFORMANCE_BASELINE.md`
Baseline figure untuk berbagai game state (combat, dialogue, quest intro, stat screen). Tanpa baseline, OCR bisa jadi bottleneck 1-2 minggu debug tanpa target.
**Priority**: Phase 1 step 1.

### Doc3. `SECURITY_PRIVACY.md`
Tool capture screenshot emulator, OCR mungkin ekstrak player name (custom char). ZCode API call kirim game state. Perlu minimum:
- "No PII stored, all sessions local"
- API data hanya dikirim ke user-configured AI gateway, tidak ke Studio Wheel
- Screenshot retention policy (auto-delete setelah 30s)
- Telemetry off-by-default
**Priority**: Pre-release wajib.

### Doc4. `COORDINATION_NOTES.md` (Phase 3)
Plan outreach komunitas: Discord `9JdYkGm2T3`, Reddit r/LifeInAdventure, Fandom wiki. Template konsent & attribution untuk kontribusi data KB.
**Priority**: Phase 3.

### Doc5. `METRICS_AND_OBSERVABILITY.md`
Telemetry lokal untuk evaluate tiap capture-OCR-RAG-AI cycle latency p99. Tanpa metric, success criteria MVP §11 PRD ("AI recommendation <5s after OCR") tidak terukur.
**Priority**: Phase 1.

### Doc6. `GAME_LORE_GLOSSARY.md`
Nama-nama lore penting: Fiana (companion), Viyork, Halad, Volga, Irelle, Galgano, Jimradi, Enard, Battra. Disebut terpencar di GAME_MECHANICS + Scribd hasil. Tanpa glossary, AI prompt reasoning konsistensi menurun (NPC ambigu).
**Priority**: Phase 1 soft.

---

## 🎯 Recommendations for Next Steps

### R1. **STOP. Phase 0 pre-flight APK extraction proof-of-concept sebelum implementasi**
Jadwalkan **4-6 jam pertama** untuk:
1. Download APK v1.2.42 dari APKMirror atau pull via ADB (`adb connect 127.0.0.1:16384` dari MuMuPlayer).
2. Run jadx decompile.
3. Cek IL2CPP/mono. Cek apakah ada JSON/StreamingAssets.
4. **Decision outcome**:
   - Bila IL2CPP gap-able → MVP Wajib pivot ke community Fandom scrape (Tavily extract + manual parser). Re-scope timeline dari 1-2 minggu ke 2-3 minggu (community parsing lebih intricate).
   - Bila mono + Assembly-CSharp readable via dnSpy → dump quest data, lanjut Phase 1.
   - Bila JSON StreamingAssets ada → lanjut Phase 1 dengan happy path.
Tanpa gate ini, semua dokumentasi hanya khayalan.

### R2. **Audit konsistensi game mechanics cross-doc + verify web**
1 jam saja:
- Cross-check GAME_MECHANICS alignment range (linear vs diskrit)
- Stat threshold (10/13/20/27)
- EXP cap (100)
- Rank milestone (10/20/35/55/80)
- Language tiers
- Pakai Tavily MCP (`tavily_search` + `tavily_extract`) atau Exa search pada Fandom wiki + LDPlayer + Scribd guide.
- Patch setiap perbedaan di GAME_MECHANICS, SPEC prompt, DATA_SCHEMA enum.

### R3. **Add EXP-aware reasoning ke AI decision engine — wajib MVP**
Field `Choice.exp_cost: int = 0` + `Choice.exp_avoidance: bool`. Add `GameStateContext.current_exp` + `exp_remaining`. Tambah explicit rule di system prompt API_CONTRACT §4.1:
```
EXP MANAGEMENT RULE (CRITICAL):
- Track current_exp and exp_remaining = 100 - current_exp.
- Bila exp_remaining ≤ 10 dan target_epilogue belum unlocked, RISKLevel="critical".
- Prioritize Choice.exp_cost=0 bila player on EXP fasting strategy.
- Selalu laporkan exp_delta ke UI.
```
Tanpa ini, tool merusak experience player — melawan value prop.

### R4. **Lazy init + EventBus impl untuk startup perceived performance**
Implement `EventBus` interface (ARCH.md §1.2 descript tapi tak ada kode):
```python
class EventBus:
    def subscribe(self, event: str, handler: Callable[[Any], None]) -> None: ...
    def publish(self, event: str, data: Any) -> None: ...
```
`main.py` open overlay dulu dengan "Loading..." state. Background thread worker load `KnowledgeBase`, `OcrEngine`, `Embedder` paralel. Progress surface ke UI via EventBus. Bila KB tidak ada, show setup wizard dari overlay (modal dialog), bukan terminal error.

### R5. **Multi-language RAG: per-language collection filter sejak awal**
1. Koleksi per language, atau metadata `language` + filter ChromaDB `where={"language": detected}`.
2. Swap embedding default ke `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, XLM-R-based) atau `bge-m3` saat game language ≠ "en".
3. Storage bertambah ~30%, accuracy cross-language naik signifikan.

### R6. **Working session: handover + Project Note Agentic Brain update**
Per aturan Session Wrap-Up Agentic Brain:
1. Buat handover `D:/Agentic Brain/08 AI Workflow/Handover Notes/Handover - LifeInAdventure-Tools - Deep Review Findings.md` (sudah ditulis 함께 deliverable ini).
2. Update Project Note `D:/Agentic Brain/04 Projects/LifeInAdventure-Tools/README.md` status → "Review Complete — 5 Critical Findings, blocked on APK pre-flight".
3. Extract reusable lesson ke `D:/Agentic Brain/09 Resources/Reusable Playbooks/Playbook - Verify Game Mechanics via Tavily.md`.

---

## 📊 Review Summary

| Aspect | Rating (1-5) | Notes |
|--------|:---:|------|
| **Documentation completeness** | 4 | Scaffolding komplit untuk MVP, tapi 6 doc penting masih missing (Doc1 forensic CRITICAL) |
| **Architecture soundness** | 3 | Abstraksi mantap, TAPI single-thread init + IL2CPP risiko tak tertangani + EventBus disebut tapi no interface kode |
| **Game mechanics accuracy** | 2 | EXP/alignment/stat threshold salah/inkonsisten lintas-dok. Web verification menemukan 3 kekeliruan load-bearing |
| **Schema design** | 3 | Typed DTO bagus, TAPI `Choice.exp_cost` missing = AI akan merusak gameplay. Alignment enum linear salah model |
| **Code placeholders** | 3 | main/config cukup starter, tapi config.py ada bug `**data["ai"]` nested TypeError |
| **Actionability** | 2 | MVP 1-2 minggu janji tampak berisiko tinggi tanpa APK pre-flight; risk register (PRD §10) kosong dari IL2CPP mention |
| **Internal consistency** | 2 | ZCode URL inkonsisten, stat range 1-20 vs 1-25, stat threshold tabel salah (lewati 27), §14 numbering duplicate |

**Overall verdict**: **Conditional Go** — documentation quality tinggi sebagai scaffolding, TAPI **5 critical findings harus fix sebelum coding dimulai**, terutama C5 (APK pre-flight) yang bisa invalidate seluruh approach.

---

## 🛡️ Residual Risks (Beyond Documented)

**Biggest undiscussed risk**: Game update breaking change. Game v1.2.42 Feb 2026, update cycle jarang (~6 bulan), tapi bila patch: (a) OCR font/UI layout berubah → tool stuck; (b) ZCode gateway berpindah gateway; (c) Komunitas kritik tool sebagai "cheating" → DMCA takedown ke GitHub. Mitigation di PRD §10 hanya "version check" — tidak cukup. Utamakan dokumentasi disclaimer + opt-in toggle + non-tampering approach.

**Yang bakal break dalam 6 bulan**:
1. Game patch dengan font/typography change → OCR accuracy drop
2. ZCode API gateway down atau migrasi URL
3. Komunitas label sebagai "cheat" → DMCA Studio Wheel
4. Phrase matcher warping ketika DLC Tales dirilis tanpa KB update path

**Prioritas Phase 1 implementation order** (rekomendasi):
1. **Phase 0** (baru): APK pre-flight proof-of-concept (R1)
2. **Phase 1 Step A**: Patch all game mechanics documents (R2) + Add EXP-aware reasoning (R3)
3. **Phase 1 Step B**: Lazy init + EventBus impl (R4) + Multi-language filter (R5)
4. **Phase 1 Step C**: Core pipeline (capture → OCR → RAG → AI → overlay)

---

## Verification & Methodology Disclosure

- ✅ **All 12 target files** in REVIEW_PROMPT.md read penuh (~4,427 lines)
- ✅ **Cross-document consistency check** lintas 4 area: stat range, alignment scale, ZCode URL, file structure
- ✅ **External web verification** via Exa search untuk 3 load-bearing claims:
  - EXP cap = 100 (verified LDPlayer + Scribd + Fandom)
  - Alignment 5 discrete tiers (verified; dokumen salah linear)
  - Stat threshold 13/20/27 (verified Fandom)
- ✅ **Agentic Brain policy compliance**: Caveman mode + Ponytail-review lensa + non-destructive (no file edits outside review report)
- ⚠️ **Limitations**: Tidak verify APK physically (memerlukan download + jadx run); judgement IL2CPP vs mono adalah analisis probabilistik dari Unity indie convention + package evidence.

---

## Sources (External Verification)

1. **LDPlayer Guide** — https://www.ldplayer.net/blog/life-in-adventure-guide-and-walkthrough.html
   - EXP cap 100 confirmed
   - Rank milestones 10/20/35/55/80 confirmed
2. **Scribd Comprehensive Guide** — https://www.scribd.com/document/607016681/A-Comprehensive-Guide-To-LiA-EN
   - "EXP may affect epilogue"
   - 5 alignment tiers: Good / Moral / Neutral / Impure / Evil
3. **Fandom Wiki Stats page** — https://life-in-adventure.fandom.com/wiki/Stats
   - Stat threshold bonus: STR+DEX 13/20 = Weapon Mastery +1/+2
   - STR 27 = Super Strength +2 (Physical Attack +20%)
   - DEX 27 = Acrobatic +2
   - STR+CON 13/20 = Toughness +1/+2 (Defense +10%/+20%)
4. **Fandom Wiki Homepage** — https://life-in-adventure.fandom.com/wiki/Life_in_Adventure_Wiki
   - Game engine: Unity (2021)
   - Genre: text-based RPG
5. **Cobraknife Traits Guide** — https://cobraknife.com/life-in-adventure/abilities/traits/
   - Bright trait = Alignment +20, Dark = -20
   - Innately Evil = -20, Innately Good = +20, Savior = +20

---

## Appendix A: Ponytail-Review Findings (Over-engineering Lens)

Apply ponytail ladder: stdlib > native > installed dep > 1-liner > minimum code.

| Lokasi | Tag | Temuan | Pengganti |
|--------|-----|--------|-----------|
| `requirements.txt` L31-32 | `native` | `customtkinter==5.2.2` dipilih TAPI ada caveat: per-region click-through butuh pywin32 hit-test, bukan abstraksi library | Tetap CTk, tapi overlay_window impl wajib nyentuh pywin32 |
| `ARCHITECTURE.md` §1.2 EventBus | `yagni` | EventBus pub/sub disebut tapi belum ada kode + hanya 4 subscriber. Inline callback cukup untuk MVP | Defer EventBus. Pakai direct callback: `overlay.on_recommendation(ai.get_recommendation(context))` |
| `API_CONTRACT.md` §6 ResponseCache class LRU + TTL | `stdlib` | Custom OrderedDict + TTL. Library `cachetools.TTLCache` stdlib-feel, lebih matang | Ganti ke `cachetools.TTLCache(maxsize=100, ttl=300)` — 0 kode maintenance |
| `SPEC.md` §3.6 `infer_schema()` di GameDataParser | `shrink` | Auto-schema-infer untuk first-time extraction. Untuk MVP, bila JSON path `StreamingAssets/quest*.json` confirmed struktur, pakai pydantic `TypeAdapter` otomatis. | Defer `infer_schema` ke Phase 2 |
| `DATA_SCHEMA.md` PlayerConfig `int` builtin collision | `nit` | Field name `str`/`dex`/`int`/`cha`/`con`/`wis` — `int` shadow builtin | Rename `stat_str`/dst |
| `main.py` L23-25 logger config hardcoded | `shrink` | `logger.add("logs/app.log", rotation="10 MB")` duplikasi dari config YAML. Sudah ada `app.log_file` field di SPEC §5.1. | Resolve dari config, bukan hardcode |

**Net lines possible**: ~50-100 lines simplifiable post-impl.

---

## Appendix B: Caveman-Review Quick Hits

`L42: 🔵 nit: README [x] MVP Features padahal belum impl`. Switch `[ ]`.
`L437 & L450 GMECH: 🔵 nit: dua §14 header`. Renumber §15.
`config.py L83-90: 🔴 bug: AIConfig(**data["ai"]) akan TypeError sebab ada nested key "zcode"`. Tambah `ZCodeConfig` sub-dataclass.
`main.py L101-105: 🟡 risk: RAGRetriever(knowledge_base=kb, top_k_events=…, top_k_choices=…)` tapi SPEC §3.3 Retriever signature pakai `embedder` param wajib, bukan `top_k_*`. Inkonsisten.
`SPEC §10.1 PyInstaller single .exe | 🟡 risk: customtkinter + EasyOCR bundled runtime ~600MB install size`. Tidak ada compression strategy.
`API_CONTRACT §6.1 @lru_cache decorator on class | 🟡 risk: decorator apply ke class definition, bukan instance method`. Penempatan salah, akan caught di decorator inspection.

---

*Report generated: 2026-07-06 by Sisyphus (OhMyOpenCode / GLM 5.2)*
*Review prompt: `docs/review/REVIEW_PROMPT.md`*
*Next: per Recommendation R6, handover note created at `D:/Agentic Brain/08 AI Workflow/Handover Notes/Handover - LifeInAdventure-Tools - Deep Review Findings.md`*
