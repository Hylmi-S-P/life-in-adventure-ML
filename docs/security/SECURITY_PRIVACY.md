---
type: governance
created: 2026-07-06
classification:
  - data_privacy
  - gdpr_compliant: false
  - retained_data:
      - screenshot_hashes
      - ocr_text_cache
      - player_stats_cache
      - ".gitignore" excludes:
        - screenshots/
        - ocr_cache/
  - transmission_risk -> zcode_api
---

# Security & Privacy Disclosures

> Tool overlaid on player MuMuPlayer/Android emulator running Life in Adventure.
> By design:
> - No PII collected (no name, no device ID)
> - No persistency beyond OCR/EXP cache RAM buffers (ephemeral retention < 60s typically)
> - Screenshot retention: only for OCR process, deleted after frame duplicate detection
> - AI model interaction: only via configruable gateway

## Data Collection Details

| Category | Contents | Retention | Legal Basis |
|----------|----------|-----------|-------------|
| Game State | Quest text, choices, EXP/alignment | RAM only, < 60s | Gameplay functionality |
| Player Input | Optional stat input (STR/DEX/etc) | Configurable (default RAM-only) | Gameplay enhancement opt-in |
| MuMuPlayer Environment | Window title, handle, resolution | Session-only | Emulator interaction minimal |
| AI Gateway Data | Quest context, player stats, ai prompt | Configurable, gdpr_disabled by default | Configurable provider interop |

**Gameplay Functionality Necessity**: OCR + RAG retrieve only for quest decisions, discarding non-quest/decision text immediately.

## AI Gateway Interaction

Default provider: ZCode via Ollagon gateway (`https://gateway.olagon.site/anthropic`).

Data sent:
- **Quest ID** (e.g., "q_main_black_guardian")
- **Raw OCR choice blocks** (original language)
- **Player stats** (if provided — opt-in via settings)
- **Knowledge base context chunks** (3·400-token)

No session cookies, no persistent client fingerprints.

## Opt-Out Provisions

Players may disable AI entirely:

```bash
python src/main.py --no-ai
```

Or select local LLM provider (Ollama):

```yaml
# configs/config.yaml
ai:
  provider: "ollama"
```

No ZCode API or OpenAI API traffic will occur in `--no-ai` mode.

## Player Choice Transparency

The overlay panel displays:
- **AI model active indicator** (e.g., "Claude Opus 4.6")
- **Gateway domain** (configurable)
- **"Data sent" toggle proof** (show sample prompt)

## GDPR Configuration

```yaml
# configs/default_config.yaml
privacy:
  gdpr_enabled: false           # False: opt-in data send; True: opt-out
  ai_gateway_legal_site: "https://olagon.privacy"   # ZCode fallback
  consent_modal: true           # Obtain explicit consent on first run
  o_keefe_logging: false         # Sanitized logging to disk
```

## Security Boundaries

- No **save file** inspection — tool only OCRs screen, never attempts save file parsing.
- No **game assets** modification — only APK extraction for KB build offline (no runtime interaction).
- No **bot capability** — purely advisory overlay, no simulated input automation.

## Incident Plan

| Incident | Immediate Messaging | Recovery |
|----------|---------------------|----------|
| ZCode gateway breach | Overlay banner ▨ GATEWAY BREACH ▨ CONSENT REVOKED | Switch fallback provider, revise default config |
| Unity APK encryption removed | None | None (game files only inspected on user-determined schedule) |
| Community claims "cheating" | None — but maintain open issue tracker for transparency | DMCA response plan ready |

## Disclaimer

> This software is for **personal educational use**.
> Not affiliated with Studio Wheel, Life in Adventure, or MuMuPlayer.
> No warranty or support provided.

Users are advised to review `config.privacy.gdpr_enabled` settings before first use.