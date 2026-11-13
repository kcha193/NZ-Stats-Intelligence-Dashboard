# Phase 4AG: ANZ source assessment (PDF versus XLSX) and PDF reader selection

14 November 2026, Pacific/Auckland. Baseline `main` `e0fd037`.

**Nothing was fetched.** Neither ANZ route was requested, probed or saved. No permission field changed. What is known about
ANZ comes from the registry's recorded evidence (`config/research_sources.toml`, verified 2026-10-25) and from the owner's
brief; what is unknown is stated as unknown. The technical comparison used **synthetic** documents only.

## 1. The two candidate routes

| | A. Quarterly Economic Outlook PDF | B. Published ANZ forecasts XLSX workbook |
|---|---|---|
| Evidence in the registry | landing page, robots and terms read directly; adapter `economic_outlook`; PDF URL shape `ANZ-QEO-YYYYMMDD.pdf`, expected every 100 days | **none**: no registry route, no recorded URL, structure or terms; the owner's brief says the research hub lists one |
| Built and tested | yes (Phase 4AF tables, Phase 4AG reader) | no |
| Permission today | `manual_import = denied`, `content_policy = metadata_only` | not evaluated; **being downloadable is not permission** |

## 2. Technical comparison on synthetic documents

The workbook experiment used a synthetic file written with a spreadsheet library (nothing from ANZ).

| Property | What was observed |
|---|---|
| Merged header cells | only the top-left cell holds the text; every other cell in the merge reads empty, so a group header ("Forecast") must be spread across its columns by a rule, as `table_grid` already does for PDFs |
| Formula cells | a cell written as a formula has **no cached value** unless a spreadsheet program last saved it; reading values returns nothing, reading formulas returns `=B3-C3`. Any workbook relying on formulas must be rejected or read only where a cached value exists |
| Percentages | a cell showing `2.5%` stores `0.025`; reading the stored value without the number format would put a fraction where a percentage belongs. A unit trap that the PDF text does not have |
| Size and structure | the archive lists its parts and uncompressed sizes **before** anything is read, so size and macro-part checks are cheap and reliable |
| Provenance | worksheet and cell addresses are exact and stable |
| Rounding | the stored number may carry more digits than the report shows; the printed forecast and the stored number can differ |

## 3. Decision matrix

Scale: 3 = clearly better, 2 = adequate, 1 = weak, 0 = unknown or blocked. Unknown is scored 0, not guessed.

| Criterion | PDF | XLSX | Reasoning |
|---|---|---|---|
| Forecast coverage (OCR, CPI, GDP, unemployment) | 2 | 0 | the PDF is the document the bank publishes its views in; the workbook's contents are unverified |
| Indicator definitions and units | 2 | 0 | PDF prints the unit beside each row; a workbook may hold fractions and codes (see above) |
| Forecast periods | 2 | 0 | both can state them; only the PDF is evidenced |
| Evidence traceability | 2 | 3 | PDF: page, row, column and the printed text; XLSX: sheet and cell address are exact |
| Formatting stability | 1 | 0 | PDF layout can move between quarters (mitigated by fail-closed reading); the workbook's stability is unknown |
| Deterministic extraction reliability | 2 | 3 if cached values present, else 0 | structured cells need no geometry; formula and format traps need explicit refusal |
| Ease of version comparison | 2 | 3 | a stable sheet layout would compare cleanly; unverified |
| Licensing and permitted use | 1 | 0 | PDF terms are read: "reproduce and store solely for viewing", not for public display; machine use is unaddressed. Workbook terms are **unread** |
| Operational maintenance | 2 | 0 | the PDF path exists, is tested and is fail-closed; an XLSX adapter would be new code, new limits and a new dependency |
| **Total** | **16** | **9, of which 6 are unverified** | |

The workbook may well be the better source: its structure is the kind of thing that extracts reliably. But the brief's test is
"equivalent reliable information **and independently authorised**", and neither is established. A decision matrix cannot
score information the project has never seen.

## 4. Decision

1. **The pilot route is the quarterly PDF**, owner-saved in a browser (the route the registry and the 4AF pilot plan already
   describe), read by the Phase 4AG reader. No XLSX adapter is built in this phase: building two ingestion routes
   "unnecessarily" is what the brief rules out, and an unauthorised, unevidenced adapter would be dead code with its own
   attack surface.
2. **The workbook stays a candidate.** The permissions request (see [the package](phase-4ag-anz-permissions-package.md)) asks
   ANZ about it by name, so the owner learns whether it may be used at the same time as the PDF.
3. **Trigger to build an XLSX adapter** (a later phase, its own review), all of: (a) ANZ's written permission names the
   workbook and the use; (b) the owner has saved one genuine workbook and inspected it; (c) it contains the four priority
   indicators with periods and actual/forecast status; (d) its values are cached rather than formulas; (e) it is stable across
   two releases. Requirements for it are recorded now so the work is ready if triggered: archive size, entry-count and
   uncompressed-size limits checked before reading; macro-enabled parts refused; formulas refused unless a cached value exists;
   percent cells read with their number format; merged cells expanded by rule; sheet, cell and workbook hash as provenance;
   the same `TableForecast` contract and the same fixed rejection codes; the same hardened child process.

## 5. PDF reader selection (the Phase 4AF limit)

Problem, reproduced: `pypdf` returns the text of one `BT..ET` block as a single string, so a row such as `OCR 3.25 3.00` drawn
as one block has no cell boundaries. Real report generators do exactly that.

| Option | Maintained | Licence | New dependencies | Hostile-input record | Evidence |
|---|---|---|---|---|---|
| `pypdf` visitor (kept for page count and encryption check only) | yes | BSD-3 | none (already present) | none known | coalesces a block into one string |
| **`pdfminer.six`** | yes (releases through 2026) | MIT | `charset-normalizer`, `cryptography` | CVE-2025-64512 (unsafe pickle loading of CMap files) fixed in 20251107; CVE-2025-70559 (incomplete fix) fixed in **20251230** | per-glyph position and advance; 0.84 s and 45 MB peak for 40 dense pages with layout analysis on (it is switched off in use) |
| `pdfplumber` | yes | MIT (metadata field empty on PyPI; MIT per distro packaging) | pdfminer.six (**exact pin**), Pillow, `pypdfium2` | inherits pdfminer's | 1.14 s and 206 MB peak on the same file; the exact pin would block the security floor; adds two binary packages |
| Custom content-stream interpreter | n/a | n/a | none | n/a | would reimplement fonts, encodings and CMaps; the brief prefers a maintained library |

**Selected: `pdfminer.six>=20251230`**, used directly (no `pdfplumber`). Resource limits are the existing child-process ones
(wall-clock timeout, bounded reply, CPU limit, and an address-space limit **that applies on Linux only**: macOS refuses it, so
there the timeout and the bounds below are the protection) plus new bounds: pages, a per-page decompressed content-stream
cap of 300,000 bytes checked **before** pdfminer lays the page out (a review showed one huge string reaching 1.5 GB before
the character count was checked), characters (1,000,000) and words (200,000). The test suite pins the installed version at
or above the floor.

Sources checked: the CVE records for pdfminer.six (NVD, Debian and SUSE trackers) and the `pdfplumber` package metadata.

## 6. What the reader does and does not do

Does: gives each cell its own word with the page, left and right glyph edge, baseline and size; keeps a raised footnote marker
on its figure as a superscript character so the figure is refused as footnoted; will not merge two figures (digits more than
0.03 em apart are two cells; a smaller gap between figure characters is treated as one number, so cells closer than that
cannot be told apart and fail closed downstream) or two period headers; reads a glyph drawn again almost on top of itself
(fake bold) once, by geometric distance; drops rotated text; leaves an unmapped glyph visible as `(cid:N)` so it cannot parse as a
number; reports prose set beside a table's rows as `mixed_layout`.

Does not: detect invisible text (render mode 3), clipped text or white-on-white text; read scanned pages (OCR of bank
reports is not authorised); read HTML tables; recover a table whose figures share a baseline with prose (it is reported and
left unread).
