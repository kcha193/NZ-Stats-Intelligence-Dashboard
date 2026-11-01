# Phase 4K — owner consent for local-only processing (approval record)

Date: 2026-11-01 (Pacific/Auckland)
Status: **two source-processing permissions approved, downstream execution still gated**.

## Owner's instruction

> yes, I approve the local-only AI processing for the pilot

This follows the assistant's explicit proposal to run one locally processed report from **NZ Treasury** and one from **RBNZ**, already manually imported in Phase 4H. Interpret this as consent to local-only processing of **these two existing documents** during the controlled pilot, **not** as authorisation for downloads, model/runtime selection, display, model calls or automated crawling. The existing registry's `llm_processing` is institution-wide, so its runtime flag must remain `denied` until execution is separately authorised and a version-scoped guard or isolated, controlled pilot configuration has been verified.

## Recorded, independent source grants

| Source | Acquisition | Permitted processing | Pilot document | Date |
|---|---|---|---|---|
| NZ Treasury | Manually imported; automated crawler remains blocked | Local-only AI processing on the owner's computer, with attribution and source-specific rights checks | Fortnightly Economic Update, 15 October 2026 (document version 1) | 2026-11-01 |
| RBNZ | Manually imported; automated crawler remains blocked | Local-only AI processing on the owner's computer, accurately attributed; no third-party material | OCR decision, 28 October 2026 (document version 2) | 2026-11-01 |

These two consents are recorded **individually in the inert approval manifest**, `config/phase-4j-pilot.json`; **no runtime processing permission has been enabled**. The unchanged source registry retains `llm_processing = "denied"` by default, `review_status = "needs_review"`, `manual_import = "approved"`, `discovery_probe = false` by default, `public_display = "none"` and `private_display = "none"` for both institutions. Existing terms/access notes still govern permitted use. A copyright licence and owner approval do **not** override a site's crawling restrictions or any third-party content rights.

## Not yet approved

All other `config/phase-4j-pilot.json` records remain **pending**:

- `selected_model_and_runtime` — the proposed Qwen3-14B Q5_K_M and pinned llama.cpp release.
- `weights_download_and_local_execution` — downloading weights/runtime, installing/building and launching `llama-server`, and making actual inference calls.
- `gold_owner_review` — a human reading the original reports and accepting/correcting baseline annotations. Technical anchor checks alone are insufficient.
- `treasury_private_display`, `rbnz_private_display`, `private_browser_ui` — anything visible in the private dashboard.

The original Phase 4J proposal manifest is still **not a runtime configuration**. The next action is a separate owner decision on the pinned runtime/model and their download/use, then reviewed annotations. Before an authorised pilot attempt, prepare a **version-limited, fail-closed** local-only processing gate so authorisation cannot silently extend to other documents from those institutions. No inference may start before those gates are cleared.

## Verification requirements before any future activation

1. The unchanged source registry continues to refuse every LLM request while `llm_processing` remains denied. Before execution, a separately reviewed version-scoped pilot gate must permit only Treasury version 1 and RBNZ version 2 with a verified loopback-only provider; a hosted provider remains refused. `research discover` and `research ingest` stay refused, and every other institution remains unchanged.
2. Confirm no `private_display` or `public_display` changes and no research in public snapshots.
3. No model weights/runtime downloaded, no LLM inference performed, no institutional network requests or production database changes in this permissions PR.
4. Have Codex independently review the scope and source-policy gate tests; do not merge automatically.

Related: [Phase 4J preflight](phase-4j-local-pilot.md) and [Phase 4I verification](phase-4i-research-quality.md).
