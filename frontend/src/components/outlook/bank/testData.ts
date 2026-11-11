/**
 * SYNTHETIC test data for the bank views: fictitious banks ("Example Bank A/B/C") and obviously invented values.
 * Real bank names never appear beside numbers in committed data.
 */
import type {
  Adjustment, BankCard, BankConsensus, BankConsensusGroup, BankForecast, BankForecasts, BankFreshness, BankRevisions,
  BankSummary, ReportKind,
} from "@/api/bank";
import type { Forecast, ForecastGroup } from "@/api/types";

export const BANKS = [
  { key: "example_a", name: "Example Bank A" },
  { key: "example_b", name: "Example Bank B" },
  { key: "example_c", name: "Example Bank C" },
] as const;

type Over = Partial<Forecast>;

export function forecast(bank: (typeof BANKS)[number], value: number | null, over: Over = {}): Forecast {
  return {
    summary_id: BANKS.findIndex((b) => b.key === bank.key) + 1,
    institution: { key: bank.key, name: bank.name, kind: "bank" },
    document_title: "SYNTHETIC outlook",
    published_on: "2026-10-01",
    indicator: "cpi_inflation",
    indicator_label: "Annual CPI inflation",
    horizon: "year to June 2027",
    value,
    unit: "percent",
    direction: "down",
    scenario: null,
    qualification: null,
    evidence: [{ section_ordinal: 1, page: 2, quote: "SYNTHETIC quote: inflation is forecast to ease" }],
    ...over,
  } as Forecast;
}

export function bankForecast(f: Forecast, over: Partial<BankForecast> = {}, kind: ReportKind = "outlook", adjustment: Adjustment = "not_stated"): BankForecast {
  return {
    forecast: f, claim_path: "forecasts[0]", report_kind: kind, adjustment, geography: "New Zealand",
    measure: f.indicator_label, forecast_author: f.institution.name, verifier_version: "verify-5",
    document_version_id: f.summary_id, ...over,
  };
}

export function group(over: Partial<ForecastGroup> & { rows: ForecastGroup["rows"] }): ForecastGroup {
  return {
    key: "cpi_inflation|percent|annual_change|year_to:2027-06|central", indicator: "cpi_inflation", indicator_name: "CPI inflation",
    unit: "percent", unit_label: "%", basis: "annual_change", basis_label: "Annual change (through the year)",
    horizon_key: "year_to:2027-06", horizon_label: "Year to June 2027", kind: "central", scenario: null,
    comparable: true, note: "", ...over,
  } as ForecastGroup;
}

const [A, B, C] = BANKS;
export const CPI_A = forecast(A, 2.1);
export const CPI_B = forecast(B, 2.4);
export const OCR_A = forecast(A, 0.0, { indicator: "ocr", indicator_label: "OCR", horizon: "March 2027 quarter" });
export const OCR_B = forecast(B, -0.25, { indicator: "ocr", indicator_label: "OCR", horizon: "March 2027 quarter" });
export const OCR_C_WEEKLY = forecast(C, 3.0, { indicator: "ocr", indicator_label: "OCR", horizon: "March 2027 quarter" });

export const FORECASTS: BankForecasts = {
  notice: "SYNTHETIC notice",
  banks: BANKS.map((b) => ({ key: b.key, name: b.name })),
  forecasts: [
    bankForecast(CPI_A), bankForecast(CPI_B), bankForecast(OCR_A), bankForecast(OCR_B),
    bankForecast(OCR_C_WEEKLY, {}, "weekly"),
  ],
  comparison: [
    {
      adjustment: "not_stated",
      comparison: {
        groups: [
          group({ rows: [{ forecast: CPI_A, earlier_vintages: [] }, { forecast: CPI_B, earlier_vintages: [] }] }),
          group({
            key: "ocr|percent|level|quarter:2027-03|central", indicator: "ocr", indicator_name: "Official cash rate",
            basis: "level", basis_label: "Level (timing within the period not stated)", horizon_key: "quarter:2027-03",
            horizon_label: "March 2027 quarter",
            rows: [
              { forecast: OCR_A, earlier_vintages: [] }, { forecast: OCR_B, earlier_vintages: [] },
              { forecast: OCR_C_WEEKLY, earlier_vintages: [] },
            ],
          }),
        ],
        excluded: [], indicators: [], institutions: [], horizons: [], note: "",
      },
    },
  ],
  excluded: [],
};

export const CARDS: BankCard[] = [
  {
    key: A.key, name: A.name, state: "ok", worst_series: null, report_name: "SYNTHETIC outlook A", published_on: "2026-10-01",
    stance: { text: "Synthetic stance: growth recovers while inflation eases.", claim_status: "clean", label: "AI interpretation" },
  },
  {
    key: B.key, name: B.name, state: "stale", worst_series: null, report_name: "SYNTHETIC outlook B", published_on: "2026-05-01",
    stance: { text: "Synthetic stance with a problem.", claim_status: "failed", label: "AI interpretation" },
  },
  { key: C.key, name: C.name, state: "permission_denied", worst_series: null, report_name: null, published_on: null, stance: null },
];

export const SUMMARY: BankSummary = { notice: "SYNTHETIC notice", cards: CARDS };

export const CONSENSUS_GROUP: BankConsensusGroup = {
  key: "cpi_inflation|percent|annual_change|year_to:2027-06|central", indicator: "cpi_inflation", indicator_name: "CPI inflation",
  unit: "percent", unit_label: "%", basis: "annual_change", basis_label: "Annual change (through the year)",
  horizon_key: "year_to:2027-06", horizon_label: "Year to June 2027", kind: "central", status: "available", n: 3,
  mean: 2.4, median: 2.4, minimum: 2.1, maximum: 2.7, range: 0.6, std_dev: 0.3, outliers_assessed: false, outliers: [],
  contributors: [
    { key: A.key, name: A.name, value: 2.1, published_on: "2026-10-01", summary_id: 1 },
    { key: B.key, name: B.name, value: 2.4, published_on: "2026-10-01", summary_id: 2 },
    { key: C.key, name: C.name, value: 2.7, published_on: "2026-10-01", summary_id: 3 },
  ],
  excluded: [], as_of: "2026-10-01", note: "", adjustment: "not_stated", title: "Consensus of banks",
  disclaimer: "Not a market consensus.",
  markers: [{ key: "example_ref", name: "Example Reference Bank", value: 2.3, published_on: "2026-09-20", summary_id: 9 }],
} as BankConsensusGroup;

export const CONSENSUS: BankConsensus = {
  consensus: { groups: [CONSENSUS_GROUP], excluded: [] },
  divergence: [
    {
      group_key: CONSENSUS_GROUP.key, indicator: "cpi_inflation", indicator_name: "CPI inflation",
      basis_label: CONSENSUS_GROUP.basis_label, adjustment: "not_stated",
      horizon_label: "Year to June 2027", unit_label: "%", spread: 0.6, median: 2.4,
      banks: [
        { key: A.key, name: A.name, value: 2.1, distance_from_median: -0.3 },
        { key: B.key, name: B.name, value: 2.4, distance_from_median: 0 },
        { key: C.key, name: C.name, value: 2.7, distance_from_median: 0.3 },
      ],
    },
  ],
};

export const REVISIONS: BankRevisions = { histories: [], excluded: [] };
export const FRESHNESS: BankFreshness = {
  exit_code: 1,
  banks: [
    {
      key: A.key, name: A.name, state: "ok",
      series: [{ series_key: "outlook", series_name: "Quarterly Outlook", state: "ok", newest_published_on: "2026-10-01",
        ingested_at: "2026-10-26T14:00:00+13:00", analysed_at: "2026-10-27T09:00:00+13:00", last_checked_at: "2026-11-10T14:00:00+13:00" }],
    },
  ],
};
