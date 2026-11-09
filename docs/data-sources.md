# Data-source registry

Phase 2A ECT was verified on 18 October 2026: official CSV ZIP, workbook and embedded chart data,
with full historical coverage and genuine August/September publication vintages.
[ECT source details and statistical reconciliation](data-sources/ect.md).

Phase 2B CPI was verified on 19 October 2026: three official CSVs, embedded charts, the workbook and the September 2026 methodology update, with Dec 2025/Mar 2026/Jun 2026 fixtures.
[CPI source details, measured tolerances and limitations](data-sources/cpi.md).

Phase 4C GDP was verified on 28 October 2026: the official quarterly CSV and the release page's growth charts, with
March and June 2026 quarter fixtures and a measured reconciliation tolerance.
[GDP source details, the three annual measures and revisions](data-sources/gdp.md).

Phase 4C labour market statistics (HLFS headline rates and the Labour Cost Index) were verified on 28 October 2026
from the official release zip, streamed, with March (revised) and June 2026 quarter fixtures.
[Labour market source details, identities and revisions](data-sources/labour-market.md).

Phase 4C Official Cash Rate (RBNZ): **blocked**, no documented access decision; a tested domain model and CSV contract
exist on synthetic data only, and nothing is acquired or shown. [OCR access assessment](data-sources/ocr.md).

Phase 3A institutional research sources (RBNZ, Treasury, banks, consultancies) were probed on 25 October 2026. They are a
separate domain with their own registry and runbook. As of 2026-11-09 (`config/research_sources.toml`): **no
institution is approved for automated access**; manual import by the owner is approved for RBNZ and Treasury only (since
31 October); hosted AI processing is permitted for Treasury only, for the operator-run `research run-policy` workflow
(since 8 November); RBNZ AI processing is denied; public display is `none` for every source.
[Research source registry, approval checklist and runbook](data-sources/research.md).

Verified on 2026-10-11 (probes) and 2026-10-12 (real-site integration check, see [progress.md](progress.md)).
Rules for every source: descriptive User-Agent, at least 10 s between requests to stats.govt.nz
(`robots.txt` crawl-delay 10; `/admin` and `/Security` are disallowed), aggressive caching, attribution
to Stats NZ (CC BY 4.0). No source in use needs credentials.

| Source | URL or path | Mechanism | Auth | Format | Cadence | Fragility |
|---|---|---|---|---|---|---|
| Release calendar (upcoming) | `/release-calendar/calendar-export/` | Official ICS export | none | iCalendar, `TZID=Pacific/Auckland`, stable UIDs | refreshed daily 06:00 NZ | Low. Has no URL or category; category comes from the title (`<Series>: <Month Year>`). |
| Releases by month | `/api/v1/releaseCalendarMonth/YYYY-MM` | JSON endpoint behind the site's own calendar | none | JSON (`PublicationDate`, `PageLink`, `Title`, `MetaDescription`) | on discovery and backfill; 2012-07 onward | **High: undocumented**; may change without notice. If it breaks, discovery degrades to ICS only and the Data health page shows it. |
| Release page | `/information-releases/<slug>/` | Embedded JSON in a `data-value` attribute | none | HTML with JSON (headline, chart series as CSV, download links) | per release | Medium: layout-versioned parser; failures classify as `layout_changed`. |
| Official data files | `/assets/Uploads/<Series>/<Release>/Download-data/*.csv` | Links found in the release page | none | CSV (also xlsx, unused) | per release | Medium. Past releases keep their files, which is what makes real vintages possible. |
| Stats NZ API Portal (ADE) | `portal.apis.stats.govt.nz` | REST | **registration and subscription key** | JSON/CSV | n/a | Not used. Endpoints not verified without a key and no vintage history. Reserved: optional Phase 2+ connector enabled only if `STATSNZ_API_KEY` is set. |

## What was observed

- **Bot protection**: the site sits behind Incapsula. A descriptive User-Agent at 10 s spacing worked in
  every probe. The fetcher classifies challenge pages as `blocked` and does not retry them hot.
- **Terms**: the terms-and-conditions page is rendered by JavaScript and could not be machine-read.
  Review it before making an instance public. Content is CC BY 4.0.
- **Migration files**: each International migration release publishes an age/sex CSV and a
  citizenship/visa/country CSV. They contain every month's mean estimate, standard error and status
  as of that release, so each release is a vintage.
- **Vintage depth**: probing releases back to 2020-09 found complete files for 2024-06 onward, then a mix
  of missing or changed layouts (quarterly files only). `backfill_since = "2024-06"` in
  `config/sources.toml` follows from that. Detail table:
  [data-sources/migration-vintage-depth.md](data-sources/migration-vintage-depth.md).
- **Provisional vs final**: taken from each file's own `status` column; the latest sixteen months are
  provisional in current files. Standard errors are zero for final estimates.
- **Calendar**: Stats NZ publishes at 10:45 Auckland time. (Observed 2026-10-11: the International migration: August
  2026 release was scheduled for 14 Oct 2026. Historical; read the stored `release` table for current dates.)
- **Corrections and re-posted releases**: the registry has no signal that a release was corrected. A release is
  identified by `<series slug>:<period label>`, and once it has a vintage no automatic path downloads it again. A
  correction under the same release page is detected only by a manual `nzstats ingest --release-key <key>` (or by
  `nzstats backfill` over a period range, which re-downloads every stored release in range), which records a new
  vintage and the `corrected` status if the parsed statistics differ. The release's `published_at` is also overwritten
  by any later calendar read that lists it as published. See
  [repository-health-review-2026-11-09.md](repository-health-review-2026-11-09.md) (findings RH-05 to RH-08).

## Adding a source

1. Verify the mechanism manually (never guess endpoints) and record it here with the date.
2. Add an adapter under `backend/src/nzstats/adapters/<category>/` with a layout version, using real file
   excerpts as fixtures (including a layout-drift case).
3. Register it in `runtime.py`, add the category to `catalog.py`, and remove it from `INACTIVE_CATEGORIES`.
