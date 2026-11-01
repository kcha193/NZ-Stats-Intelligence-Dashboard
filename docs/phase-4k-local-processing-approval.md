# Phase 4K — owner consent for local-only processing (approval record)

Date: 2026-11-01 (Pacific/Auckland)
Status: **two source-processing permissions approved, downstream execution still gated**.

## Owner's instruction

> yes, I approve the local-only AI processing for the pilot

This follows the assistant's explicit proposal to run one locally processed report from **NZ Treasury** and one from **RBNZ**, already manually imported in Phase 4H. Interpret this only as permission to set the research registry's `llm_processing = "local_only"` for those two sources, **not** as authorisation for downloads, model/runtime selection, display, model calls or automated crawling.

## Recorded, independent source grants

| Source | Acquisition | Permitted processing | Pilot document | Date |
|---|---|---|---|---|
| NZ Treasury | Manually imported; automated crawler remains blocked | Local-only AI processing on the owner's computer, with attribution and source-specific rights checks | Fortnightly Economic Update, 15 October 2026 (document version 1) | 2026-11-01 |
| RBNZ | Manually imported; automated crawler remains blocked | Local-only AI processing on the owner's computer, accurately attributed; no third-party material | OCR decision, 28 October 2026 (document version 2) | 2026-11-01 |

These grants are recorded individually in `config/research_sources.toml` and `config/phase-4j-pilot.json`. The registry preserves `review_status = "needs_review"`, `manual_import = "approved"`, `discovery_probe = false` by default, `public_display = "none"` and `private_display = "none"` for both institutions. Existing terms/access notes still govern permitted use. A copyright licence and owner approval do **not** override a site's crawling restrictions or any third-party content rights.

## Not yet approved

All other `config/phase-4j-pilot.json` records remain **pending**:

- `selected_model_and_runtime` — the proposed Qwen3-14B Q5_K_M and pinned llama.cpp release.
- `weights_download_and_local_execution` — downloading weights/runtime, installing/building and launching `llama-server`, and making actual inference calls.
- `gold_owner_review` — a human reading the original reports and accepting/correcting baseline annotations. Technical anchor checks alone are insufficient.
- `treasury_private_display`, `rbnz_private_display`, `private_browser_ui` — anything visible in the private dashboard.

The original Phase 4J proposal manifest is still **not a runtime configuration**. The next action is a separate owner decision on the pinned runtime/model and their download/use, then reviewed annotations. No inference may start before those gates are cleared.

## Verification requirements before any future activation

1. Source registry parses and tests preserve: local provider admitted for the two manually imported documents, hosted provider refused, `research discover` and `research ingest` still refused, every other institution unchanged.
2. Confirm no `private_display` or `public_display` changes and no research in public snapshots.
3. No model weights/runtime downloaded, no LLM inference performed, no institutional network requests or production database changes in this permissions PR.
4. Have Codex independently review the scope and source-policy gate tests; do not merge automatically.

Related: [Phase 4J preflight](phase-4j-local-pilot.md) and [Phase 4I verification](phase-4i-research-quality.md).
