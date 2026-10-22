# Visual storytelling redesign

Status: implemented on `feat/visual-stories` (2026-10-23). Phases 1 to 3 below.
Scope: frontend and presentation only. No change to ingestion, adapters, validation, scheduling, the SQLite
schema, revision semantics or any API contract.

## 1. Goal

Make the latest official statistics understandable in about ten seconds, and give each finding a stable,
linkable, exportable page. The reference for information hierarchy is editorial data storytelling
(Voronoi, Visual Capitalist, central-bank and statistics-office chart packs): one claim per graphic, a
headline that states the finding, a large number with its unit, a chart that answers one question, and the
source on the graphic itself. No Voronoi layouts, graphics, branding or assets are copied; the reference
site was not inspected for this work, so only its general editorial principles are used.

## 2. Existing architecture (as found on `main` at `11851b0`)

- Routes: `/` Overview, `/migration`, `/inflation`, `/electronic-card-transactions`, `/releases/:id`,
  `/calendar`, `/health`. Pages are lazy-loaded inside `Layout`.
- Data: TanStack Query hooks in `src/api/hooks.ts` over a read-only FastAPI. One request returns a whole
  CPI bundle (`/api/cpi`) or ECT bundle (`/api/ect`); migration is read per series (`/api/series/:key`),
  with bundle identity checked client-side before two series are combined.
- Charts: ECharts 6 option builders (`src/charts/options.ts`, `cpi.ts`, `ect.ts`) rendered by `EChart` and
  wrapped by `ChartCard` (title, question, unit, source, caveat, CSV, PNG with caption, data table).
- Insights: the backend's deterministic `ReleaseAnalysis` (executive summary, context, revisions,
  corrections, methodology) with `Evidence` rows (series key, period, value, release key).
- Palette: validated categorical/positive/negative tokens in `index.css` (light and dark), read by
  `useChartTheme`.

### Gaps

- The Overview is a wall of ten equal KPI cards; nothing says what changed or why it matters.
- Findings exist only inside long dashboards; there is no linkable page for one finding.
- PNG export is chart-shaped (variable width, caption appended), not a presentation format.
- No editorial type scale; headings and numbers share one size ramp.

## 3. Information architecture

| Route | Purpose |
|---|---|
| `/` | Masthead, featured story, headline indicators, story collection, latest releases, upcoming releases, freshness. Every existing panel is retained. |
| `/stories` | Feed of every story the current data supports, filterable by category. |
| `/stories/:id` | One story: headline, key statistic, infographic, explanation, context, evidence, source and methodology, dashboard link, export and share. |

Existing routes are unchanged. Navigation gains "Stories".

### Story identifiers

`<template>-<reference period>`, for example `inflation-annual-2026-06`. The template is a fixed editorial
slot and the period is the reference period of the data used, so an identifier always means the same
statistic. When a newer release replaces the data, the old URL resolves to a "superseded" notice that links
to the current story for the same template; it never silently shows newer numbers under an old address.
Earlier vintages are not re-rendered because the CPI and ECT endpoints serve only the latest bundle.

## 4. Story engine (`src/stories/`)

Pure functions turn API payloads into typed `Story` objects. No LLM, no free text from upstream except
release titles and backend insight text (rendered as text, never HTML).

- `cpi.ts`: annual inflation, contributions to the change (quarterly and annual), tradables versus
  non-tradables. Contributions are read only from the published contribution blocks, in percentage
  points; component price changes are never presented as contributions.
- `ect.ts`: retail spending monthly change (published seasonally adjusted change series), industry
  movements (seasonally adjusted, same period, adjacent months within one release).
- `migration.ts`: year-ended net migration, arrivals versus departures, NZ versus non-NZ citizens. All
  year-ended; monthly series are not used in these stories, so the two are never mixed. Series are
  combined only when they come from the same release bundle.
- `text.ts`: deterministic wording. Direction words come from the value as displayed (rounded to the
  shown precision), so the words never disagree with the number. Rates change by percentage points; levels
  change by percent and by their own unit.
- `engine.ts`: assembles stories, orders them by publication date then editorial priority, de-duplicates
  identifiers and resolves `/stories/:id` (found, superseded, or not found).

A builder returns no story when its inputs are missing or not usable (unavailable contribution block,
missing series, no comparison period, mixed bundles). Missing categories simply have no stories; nothing is
synthesised.

Each story carries: headline, dek, key statistic (value, unit, label, sign), reference period, status,
release provenance (id when known, key, title, published and captured instants, page URL, status), an
explanation, context bullets, caveats, methodology, evidence rows (series key, period, value, unit, status,
release key), the backend insights for that release where available, a thumbnail spec and a figure spec.

## 5. Components (`src/components/story/`)

`KeyStatistic`, `StoryCard`, `StoryGrid`, `StoryHero`, `MiniChart` (inline SVG thumbnail), `SourceAttribution`,
`DataEvidencePanel`, `StoryExport`, `StoryFigure`. The main infographic reuses `ChartCard` and the existing
option builders; story figures only add annotations (latest value, peak in range) and choose the window.

## 6. Visual grammar

- Type: IBM Plex Sans throughout (already self-hosted). Editorial scale: kicker 12px uppercase tracked;
  story headline 28 to 44px semibold, tight leading; key statistic 48 to 64px tabular; body 16px at 65ch.
- Colour: neutral surfaces, one accent (the existing chart navy) for kickers, rules and the featured
  frame. Series colours, positive/negative and provisional tokens are the validated set already in
  `index.css`; no new chart colours were introduced.
- Signed values: positive and negative bars use the validated positive/negative pair with a zero line, and
  labels carry an explicit sign and unit (`+0.82 pp`, `−2.3%`).
- Rates use `%`; changes in rates use percentage points, spelled out in prose and `pp` in tight labels.
- A non-zero baseline is stated on the chart itself. No dual axes, no area-based encodings of signed data,
  no treemaps (a ranked bar reads more accurately for eight industries).
- Motion: none beyond hover states; `prefers-reduced-motion` already disables transitions.

## 7. Export

`StoryExport` renders a 1200 × 675 (landscape) or 1200 × 1500 (portrait) PNG. The chart is re-rendered
off-screen by ECharts at the exact panel size from the same option the page shows, so nothing is cropped
or scaled. Text is laid out by a pure function (`exportLayout.ts`, unit-tested with a fake text measurer)
and drawn on canvas: kicker, headline, key statistic, chart, unit, reference period, caveat, source,
publication date, release URL and attribution. Text that would not fit is truncated with an ellipsis in
the secondary caption only, never in the headline, statistic or source line; the layout test asserts this.
Colours follow the current light or dark theme. Sharing uses the Web Share API when present, otherwise
copies the link.

## 8. Data contract

No API change. Stories use `/api/cpi`, `/api/ect`, `/api/series/{mig.ry.net, mig.ry.arrivals,
mig.ry.departures, mig.ry.net.nz, mig.ry.net.nonnz}`, `/api/overview` and `/api/releases`. A 404 from a
category endpoint means "not ingested" and removes that category's stories.

Gaps documented rather than invented:

- Migration country ranking is a derived total; it stays on `/migration` and is not a story yet.
- Revision (vintage) comparison stories need per-vintage CPI/ECT reads that the API does not offer.
- Migration has no backend insight block in the series payload; its evidence panel lists exact points.

## 9. Delivery phases

1. Tokens and type scale, story components, homepage, `/stories`, CPI annual-inflation story (vertical slice).
2. CPI contributions and tradables, ECT retail and industries, migration net, flows and citizenship.
3. PNG export (both formats), share, mobile refinements, annotations, accessibility, visual review.

## 10. Test strategy

- Unit (Vitest): wording rules, each builder against the real fixtures (headline/series mapping, signs,
  units, pp vs %), omission on missing or unusable inputs, superseded resolution, export layout bounds.
- Component: feed, story page, homepage with empty, partial (one category 404), corrected and stale data.
- Playwright (offline seeded DB): navigation, story pages per category on desktop/tablet/mobile, no
  horizontal scroll, PNG dimensions for both formats, existing suites unchanged.
- Screenshots inspected at 1440, 768 and 390 px in light and dark.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Headlines overstate (causal language, "record") | Fixed templates; verbs limited to rose/fell/held, "contributed", "led"; "last this high" computed from the series. |
| Wording disagrees with the rounded number | Direction derived from the displayed value. |
| Stale data presented as new | Every card shows reference period and publication date; a newer scheduled-but-unverified release is called out on the story page. |
| Old story URL silently shows new numbers | Superseded resolution. |
| Mixed vintages in one graphic | Bundle identity check before combining migration series. |
| Export truncation | Fixed-size off-screen chart and layout tests. |
| Bundle size | No new dependencies; story pages lazy-loaded. |

## 12. Remaining backlog

- Flag "newer release published but not verified" on homepage cards and the hero, not only on the story page.
- Migration country story (derived ranking, labelled as derived) and a revision (vintage) story once the API can
  serve a named earlier vintage for CPI and ECT.
- Quarterly ECT story (published quarterly series exist; not yet used).
- Optional 2× export for high-density screens (formats are currently exact 1200-pixel widths).
- Mobile primary navigation scrolls horizontally; a compact menu would expose all destinations at 390 px.
- Homepage still shows all ten KPI cards; consider a compact indicator table with the cards behind a disclosure.
- Code-split ECharts (existing bundle-size warning).
