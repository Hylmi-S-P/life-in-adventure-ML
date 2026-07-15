# 🔍 Agent Code Review Prompt — LifeInAdventure-Tools

> Use this prompt with another AI agent to review everything built in this session.

---

## Review Request

Kamu diminta untuk review dokumen-dokumen project **LifeInAdventure-Tools** — sebuah AI-powered overlay companion untuk game "Life in Adventure" text-based RPG. Baca semua file yang ditandai ✅ di bawah, lalu berikan feedback komprehensif.

---

## Files to Review

### Start with these (READ FIRST):
1. `D:/LifeInAdventure-Tools/HANDOVER.md` — Session summary & context
2. `D:/LifeInAdventure-Tools/README.md` — Project overview

### Then review these (MAIN CONTENT):
3. `D:/LifeInAdventure-Tools/SPEC.md` — Technical specification
4. `D:/LifeInAdventure-Tools/docs/prd/PRD.md` — Product requirements
5. `D:/LifeInAdventure-Tools/docs/architecture/ARCHITECTURE.md` — Deep architecture
6. `D:/LifeInAdventure-Tools/docs/data/GAME_MECHANICS.md` — Game mechanics (recently researched)
7. `D:/LifeInAdventure-Tools/docs/data/DATA_SCHEMA.md` — Data schema
8. `D:/LifeInAdventure-Tools/docs/api/API_CONTRACT.md` — AI API contract
9. `D:/LifeInAdventure-Tools/docs/setup/SETUP_GUIDE.md` — Setup guide
10. `D:/LifeInAdventure-Tools/requirements.txt` — Dependencies
11. `D:/LifeInAdventure-Tools/src/main.py` — Main entry point (placeholder)
12. `D:/LifeInAdventure-Tools/src/config.py` — Config loader (placeholder)

---

## Review Checklist

### A. Documentation Quality (Primary Focus)
- [ ] **Completeness**: Apakah semua aspek penting sudah tercover?
- [ ] **Accuracy**: Apakah ada factual errors? (terutama di GAME_MECHANICS.md)
- [ ] **Consistency**: Apakah ada contradictions antar dokumen?
- [ ] **Clarity**: Apakah cukup jelas untuk developer baru yang join project?
- [ ] **Actionability**: Apakah seseorang bisa langsung mulai coding dari dokumen ini?

### B. Architecture & Design
- [ ] Apakah arsitektur sudah masuk akal untuk MVP?
- [ ] Apakah tech stack choices sudah justified?
- [ ] Apakah ada missing components atau edge cases?
- [ ] Apakah error handling strategy sudah cukup?

### C. Game Mechanics (GAME_MECHANICS.md)
- [ ] Apakah semua mechanics yang ditemukan dari research sudah accurate?
- [ ] Apakah ada mechanics yang MISSING yang seharusnya ada?
- [ ] Apakah formulas (damage, stat modifier, EXP) sudah benar?
- [ ] Apakah "Open Questions" section sudah lengkap?

### D. Data Schema (DATA_SCHEMA.md)
- [ ] Apakah semua entities sudah cukup untuk MVP?
- [ ] Apakah relationships antar entities sudah clear?
- [ ] Apakah ChromaDB collections design sudah optimal?
- [ ] Apakah ada missing fields yang critical?

### E. Code Placeholders (src/)
- [ ] Apakah main.py placeholder sudah cukup sebagai starting point?
- [ ] Apakah config.py design sudah flexible?
- [ ] Apakah module separation sudah logis?

### F. Risks & Gaps
- [ ] Apa biggest risks yang TIDAK disebutkan di dokumen?
- [ ] Apa yang bisa break dalam 6 bulan?
- [ ] Apa yang perlu diprioritaskan di Phase 1 implementation?

---

## Output Format

Strukturkan review kamu seperti ini:

```
## ✅ What Was Done Well
(3-5 bullet points)

## ⚠️ Issues & Gaps

### Critical (Must Fix Before Implementation)
### Important (Should Address in Phase 1)
### Minor (Nice to Have)

## 📋 Missing Documentation
(Things that should exist but don't)

## 🎯 Recommendations for Next Steps
(3-5 concrete, actionable recommendations)

## 📊 Review Summary
| Aspect | Rating (1-5) | Notes |
|--------|:---:|------|
| Documentation completeness | | |
| Architecture soundness | | |
| Game mechanics accuracy | | |
| Schema design | | |
| Code placeholders | | |
| Actionability | | |
```

---

## Context untuk Reviewer

**Game**: Life in Adventure — text-based D&D-style RPG by Studio Wheel (Korea)
**Package**: `com.StudioWheel.Bard` | **Version**: 1.2.42
**Discord**: discord.gg/9JdYkGm2T3 | **Reddit**: r/LifeInAdventure

**Goal MVP**: Overlay tool yang auto-capture layar game, OCR text, RAG query, AI recommendation
**Emulator**: MuMuPlayer
**AI**: ZCode API (Claude via Ollagon gateway)
**Target user**: Pemain yang mau optimalisasi pengalaman tanpa trial-error

**Key insight about the game**:
- Game berbasis teks dengan pixel art
- Setiap pilihan dipengaruhi 6 stats (STR/DEX/INT/CHA/CON/WIS)
- D20 roll + stat modifier vs DC untuk stat checks
- **CRITICAL**: EXP bar kalau penuh = ending terpicu early
- Alignment system (-100 to +100) mempengaruhi epilogue unlock
- Backgrounds = DLC yang mengubah main storyline

---

## Additional Context dari Session

During the brainstorming session, the user confirmed:
1. MuMuPlayer emulator — YES
2. Screen capture approach (overlay panel) — MVP confirmed
3. **User tidak punya spreadsheet komunitas** — jadi APK extraction diperlukan
4. **User bilang "analisis data baru" = ambicioso dan menarik** — berarti extraction from scratch itu yang diinginkan
5. Game update freq sangat jarang (sekitar 6 bulan) — APK re-extraction manageable
6. Tavily MCP sudah tersedia di environment (API key: tvly-dev-...)
7. ZCode API sudah configured (Ollagon gateway, claude-opus-4-6)

**Budget/preference**: MVP dulu, keep it simple, achievable in 1-2 weeks

---

*Use Tavily MCP if you need to verify any game mechanics claims against current web sources.*
