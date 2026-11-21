# Phase 4AR plan: ANZ canonical series mapping (interpreter `xlsx-anz-4`)

Spec: [Phase 4AQ §3](../../phase-4aq-anz-canonical-series.md). The owner approved the design on 22 November 2026.
The owner's six answers (§2.1 A to F) are still pending, so this plan builds and tests the mechanism on synthetic
workbooks only. The real pilot (Stage 6) waits for those answers. No GDP or CPI block is chosen by an agent.

## Tasks (TDD: each test is watched failing first)

1. **Manifest parsing** (`research/xlsx_mapping.py`). Strict schema `anz-workbook-mapping-1`, exact key sets,
   size-bounded JSON. Fixed codes `mapping_invalid`, `mapping_duplicate` and `mapping_hash_mismatch`. OCR, unknown
   bases, unit evidence on any series other than unemployment, and unit evidence on another sheet are invalid. The
   mapping hash is the SHA-256 of the file bytes.
2. **Interpreter `xlsx-anz-4`** (`research/xlsx_anz.py`, `mapping=` argument). Without a manifest, the path is
   unchanged and pinned against the pre-change golden codes (`fdc24865` and `439ccf98`). With a manifest:
   - check the structure per entry (`mapping_structure_mismatch`);
   - exempt only listed columns, and refuse every other column naming a mapped indicator as `not_canonical_series`;
   - check the indicator (`mapping_indicator_mismatch`) and the basis (`mapping_basis_mismatch`);
   - keep every existing rule;
   - accept the unemployment unit only from verified unit evidence;
   - apply the reviewed sheet context;
   - add provenance to the evidence.
3. **Stored revalidation** (`table_context.evidence_texts`). Honour `caption_review` only when its classification is
   `editorial`, its sheet name equals the caption, and its mapping hash equals the evidence's `mapping_sha256`.
4. **Ingest and storage gate** (`table_ingest`). Add `mapping=` to extraction. Refuse the whole manifest on a hash,
   schema or publication-cell mismatch. The confirmation code covers `mapping_sha256`. The stored interpreter is
   `xlsx-anz-4`, and the input digest covers the cells and the mapping.
5. **Consumers**: `CURRENT_INTERPRETERS`, the `_VERSIONS` placeholders and `HISTORY_UNVERIFIED` gain `xlsx-anz-4`.
6. **Owner command** `tables map V --series ... --out FILE`. It builds the manifest from positions only, refuses to
   overwrite an existing file, and prints only the file's SHA-256 and counts. `tables extract V --mapping FILE` applies
   the manifest.
7. Full backend suite, ruff, independent review, docs (`docs/phase-4ar-…`, `progress.md`, `CLAUDE.md`), and a PR.
