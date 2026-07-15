---
type: monitoring
category: operations
created: 2026-07-07
status: draft
replaces: N/A
---

# Metrics & Observability

> Monitoring, logging, and performance-tracking infrastructure for the LifeInAdventure-Tools pipeline. Establishes defaults for alerting thresholds, structured logging, and health-check endpoints.

---

## 1. Core Principles

- **Local-first**: All metrics are stored locally (no cloud dependency for MVP).
- **Privacy-safe**: No PII shipped to external endpoints; only anonymous aggregated counters.
- **Opt-in telemetry**: Backend health checks are opt-in via `config.telemetry.enabled`.

---

## 2. Pipeline Stages (Instrumentation Points)

Each stage emits a `PipelineEvent` with timing, success/failure, and payload size:

| Stage | Event Name | Key Metrics | Error Classification |
|-------|-----------|-------------|----------------------|
| Screen Capture | `capture.completed` | latency_ms, width, height, duplicate_hash | CaptureError |
| OCR Processing | `ocr.completed` | latency_ms, char_count, word_count, language | OCRError, OCRTimeoutError |
| Text Normalization | `normalize.completed` | latency_ms, corrections, dedup_hit | NormalizationError |
| RAG Retrieval | `rag.completed` | latency_ms, chunks_retrieved, score_max, score_min | RAGNoMatchError, RAGTimeoutError |
| AI Recommendation | `ai.completed` | latency_ms, tokens_in, tokens_out, provider | AIProviderError, AIRateLimitError |
| Overlay Render | `overlay.updated` | latency_ms, panel_count | OverlayError |

---

## 3. Structured Logging

Using `loguru` (pre-configured in SPEC.md §8.1):

```python
# configs/default_config.yaml
logging:
  level: "INFO"               # DEBUG | INFO | WARNING | ERROR | CRITICAL
  format: "{time} | {level} | {name}:{function}:{line} | {message}"
  rotation: "10 MB"
  retention: "7 days"
  path: "logs/lifeinadventure-tools.log"
  telemetry:
    enabled: false            # Opt-in anonymous usage stats
    endpoint: ""              # Set URL for remote log shipping (MVP: empty = local only)
```

Log file structure:

```
logs/
├── lifeinadventure-tools.log       # Rotating main log
├── errors.log                       # ERROR+ level only (for triage)
├── pipeline_stats.jsonl             # Structured per-event metrics
└── crash_reports/                   # Automatic crash dump on unhandled exceptions
    └── crash_20260707_143022.dmp
```

---

## 4. Latency Budget (Per-Component)

Derived from SPEC.md §7 Performance Requirements:

| Component | p50 Target | p95 Target | p99 Max | Notes |
|-----------|-----------|------------|---------|-------|
| Screen Capture | 150ms | 200ms | 500ms | ~3 FPS burst |
| OCR Processing (EasyOCR) | 800ms | 1.5s | 3.0s | CPU mode; GPU halves this |
| Text Normalization | 30ms | 50ms | 100ms | Regex + dedup hash |
| RAG Retrieval | 200ms | 500ms | 800ms | ChromaDB query |
| AI Recommendation | 2.0s | 5.0s | 8.0s | Varies by provider/model |
| **Total Pipeline** | **3.2s** | **7.3s** | **12.0s** | End-to-end; adaptive capture may extend |

---

## 5. Health Check Endpoints (Local-Only)

For debugging via `localhost` during development:

```python
# Exposed via aiohttp in dev mode (not in production MVP)
GET /health          → {"status": "ok", "uptime": 3600, "version": "0.1.0"}
GET /health/stages   → {"capture": true, "ocr": true, "rag": true, "ai": true}
GET /health/latency  → {"p50": 3.2, "p95": 7.3, "p99": 12.0}  # rolling window
```

---

## 6. Alert Thresholds (Recommended)

When a component exceeds these thresholds consecutively (3+ times), log a `WARNING`:

| Condition | Severity | Action |
|-----------|----------|--------|
| OCR latency > 3.0s × 3 consecutive | WARNING | Log diagnostic; extend capture interval |
| AI latency > 8.0s × 3 consecutive | WARNING | Fallback to cached response if available |
| RAG returns 0 chunks | WARNING | Fallback to KB-not-loaded state |
| Capture → Overlay total > 15s | ERROR | Halt pipeline; restart capture loop |
| Memory > 800MB | ERROR | Suggest user reduce capture quality |
| Unexpected exception in any stage | CRITICAL | Dump crash report; attempt safe restart |

---

## 7. Dashboard (Future — Post-MVP)

Not implemented for MVP, but schema ready:

```yaml
# configs/dashboard_config.yaml
dashboard:
  enabled: false
  refresh_interval: 5s
  panels:
    - name: "Pipeline Latency (p50/p95/p99)"
      type: line_chart
      source: "pipeline_stats.jsonl"
    - name: "Component Health"
      type: status_grid
    - name: "OCR Accuracy (rolling WER)"
      type: gauge
      min: 0
      max: 100
```

---

## 8. Debugging Mode

```bash
# Run with verbose logging + stacked trace on errors
python src/main.py --verbose

# Run performance benchmark (no UI)
python tests/test_perf_pipeline.py --iterations 50

# Watch pipeline stats in real-time
tail -f logs/pipeline_stats.jsonl | python -m json.tool
```

---

## 9. References

- SPEC.md §7: Performance Requirements & Benchmarks
- OCR_PERFORMANCE_BASELINE.md: Per-fixture OCR timing
- REVIEW_REPORT.md I2: Adaptive capture interval rationale
