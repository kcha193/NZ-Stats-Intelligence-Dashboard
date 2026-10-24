# Visual stories 2.0: editorial redesign

Status: implemented on `feat/visual-stories-v2` (2026-10-24). Builds on
[visual-storytelling-redesign.md](visual-storytelling-redesign.md); everything there still holds unless changed here.
Scope: frontend only. No change to ingestion, adapters, validation, scheduling, the SQLite schema, revision semantics
or any API contract. Stories are still deterministic functions of the API payloads.

## 1. Audit (pre-change, `main` at `64b0f3b`)

Rendered against the offline seeded database at 390, 768, 1280 and 1440 px, light and dark.

| Area | Finding (evidence) |
|---|---|
| Hierarchy | Ten KPI cards of equal weight sat directly under the lead (1440: rows 2 to 4 of the first two screens). Nothing said which number mattered most. |
| Mobile | The homepage was 7,077 px tall at 390 px, more than half of it KPI cards; the hero was followed by a full screen of cards before any story. The primary nav scrolled sideways with seven items. |
| Story thumbnails | 160 × 56 SVGs drawn with `preserveAspectRatio="none"` and no labels: no values, periods or units. The tradables thumbnail showed tradables only; arrivals/departures and citizenship were two unlabelled lines. |
| Repetition | Every story was the same bordered card; every panel was a bordered rectangle (stories, KPIs, releases, freshness). |
| Readability | No explanation of CPI, percentage points, seasonal adjustment, net migration or provisional estimates on the homepage. Muted text (`oklch 0.556`) fell to about 4.2:1 on tinted surfaces. |
| Operations | Release lists and freshness carried the same visual weight as the findings. |
| Duplication | The net-migration trend chart duplicated the migration story graphic on the same page. |

## 2. Direction

A New Zealand economic publication: one display face for headlines and the one big number, a cool neutral page, one
accent ink, and graphics drawn for the story they tell. Dials (CLAUDE.md, spec §9): DESIGN_VARIANCE 5,
MOTION_INTENSITY 2, VISUAL_DENSITY 7.

- Type: Geist Variable (already installed, now self-hosted) for masthead, headlines, section titles and key figures;
  IBM Plex Sans for body, labels, tables, annotations and sources. Utilities `type-masthead`, `type-lead`,
  `type-section`, `type-card`, `type-figure`, `type-note` in `index.css`.
- Colour: neutral surfaces plus `--surface-feature` (faint accent wash for the lead) and `--surface-sunken` (the
  record and operations bands). Accent ink unchanged. Category tones reuse the validated chart colours
  (amber, violet, teal) and appear only as a 3 px rule or a 6% wash beside a written category name: never text,
  links or a data series on the same graphic. No new chart colours. Muted text darkened to `oklch 0.49`
  (about 5.6:1 on the feature surface).
- Shape: panels and cards 8 px radius; editorial sections are unboxed and separated by rules and space.
- Motion: a 2 px hover lift on story cards and a 150 ms fade on explainers. `prefers-reduced-motion` removes both;
  nothing is revealed by animation.

## 3. Homepage

1. Masthead: "New Zealand's economy, explained.", supporting line, latest ingestion time and next scheduled release.
2. The economy at a glance: three measures from the headline story of each category (`Story.glance`), each with value,
   measure (an explainer), reference period, movement against the proper comparator and one plain sentence.
   - Inflation: rate against last quarter's rate in percentage points; "Consumer prices were X% higher/lower than a year
     earlier" from the sign of the displayed annual rate, so easing inflation is never "falling prices".
   - Retail card spending: the published seasonally adjusted monthly change, with the previous month's change.
   - Net migration: year-ended total against the non-overlapping year a year earlier.
3. Featured story: asymmetric band on the feature surface. Headline, dek, the key figure at display size, the first
   context line as the comparison, solid "Read the story" plus the dashboard link, and the story's own chart (same
   option as the story page) with unit, caveat, source and key terms.
4. What's changing: one prominent card (large graphic), two supporting cards (number beside graphic), then the rest in
   balanced rows (`arrangeCollection`; picks avoid repeating the lead's category).
5. Explore by topic: three wide rows (prices, spending, people) with what is measured, the newest finding and links to
   stories and the dashboard.
6. Key indicators: grouped by topic, first indicator per topic shown, "Explore all N indicators" disclosure.
7. Releases and data quality (sunken band): featured release, latest and upcoming releases, freshness summary with
   details on demand, inactive categories.

The duplicate net-migration trend chart was removed from the homepage; the migration story and `/migration` carry it.

## 4. Story graphics (`StoryGraphic`, `Thumb`)

Drawn as SVG with real text at true pixel size (the container is measured; labels never shrink with the column).

| Story | Encoding |
|---|---|
| Annual inflation | Line, zero baseline, latest value and ten-year peak labelled |
| Contributions | Diverging ranked bars in pp; compact cards show the largest six and say so |
| Tradables | Dumbbell on one % axis through 0%, gap stated in pp |
| Retail change | Signed monthly columns, latest labelled, extremes labelled |
| Industries | Diverging ranked bars in % |
| Net migration | Year-ended line, provisional segment dashed and keyed, peak labelled "YE" |
| Arrivals vs departures | Two bars from zero (counts), difference stated |
| Citizenship | Diverging bars, signed net flows |

Each graphic has a text alternative listing the values it labels (`describeThumb`). Story-page charts gain latest-bar
emphasis (retail) and value end labels (tradables); the migration peak annotation now reads "YE Oct 2023".

## 5. Audience layers

- Simple: glance sentences, headlines, deks.
- Curious: charts, "In context", key-term explainers (`Term`, click or tap, Escape closes, focus returns).
- Expert: "Data, definitions and sources" band on each story: evidence table, release findings, methodology, source.
- Glossary (`stories/glossary.ts`): CPI inflation, annual vs quarterly, lower inflation is not falling prices,
  percentage points, contribution, tradables, seasonally adjusted, nominal values, net migration, year-ended totals,
  provisional, revisions. Definitions carry no figures and no causal claims.

## 6. Navigation

Home, Stories and an "Explore data" disclosure (Dashboards: Inflation, Card spending, Migration; Releases and data
quality: Release calendar, Data health). Below 640 px one "Menu" disclosure holds every destination. Disclosure
pattern (button plus links), not an ARIA menu. Escape, outside click and navigation close it. The footer lists every
page. No route changed.

## 7. Story pages

Header with the key figure beside the headline; chart with export and share directly beneath; "In context" and key
terms beside it; explanation and caveats; the record band; related stories (same topic first); previous/next.
Navigating between stories remounts the page so a chart variant never carries over.

## 8. Exports

Unchanged sizes (1200 × 675, 1200 × 1500) and provenance. Headline, statistic and chart title now use the display
face; the landscape card sets the dek in the story column when it fits whole (it is never shortened, and never at the
cost of a headline below 28 px). Only the caveat can still be truncated.

## 9. Remaining limitations

- Homepage scroll length at 390 px grew (about 9,600 px) because the glance and topics are new layers; the first screen
  is now the masthead and glance rather than KPI cards.
- Glance covers the three categories with verified sources; others appear when their stories exist.
- Category tones on a 6% wash are subtle in dark mode by design.
- The ECharts bundle-size warning is unchanged.
- Revision (vintage) stories still need per-vintage CPI and ECT endpoints.
