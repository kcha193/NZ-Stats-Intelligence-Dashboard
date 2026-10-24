import type { TermKey } from "./glossary";
import type { StoryCategory } from "./types";

/** Reader-facing topics. Descriptions say what is measured, never why it moved. */
export const TOPICS: Record<StoryCategory, {
  title: string; blurb: string; measured: string; dashboard: { to: string; label: string }; term: TermKey; tone: string; wash: string;
}> = {
  inflation: {
    title: "Prices and cost of living", blurb: "Understand inflation and the prices households pay.",
    measured: "Consumers price index (CPI), published quarterly", dashboard: { to: "/inflation", label: "Explore inflation" },
    term: "cpi", tone: "bg-cat-inflation", wash: "bg-cat-inflation/6",
  },
  spending: {
    title: "Spending and retail", blurb: "See how spending on electronic cards is changing, month by month.",
    measured: "Electronic card transactions, published monthly", dashboard: { to: "/electronic-card-transactions", label: "Explore card spending" },
    term: "seasonally-adjusted", tone: "bg-cat-spending", wash: "bg-cat-spending/6",
  },
  migration: {
    title: "People and migration", blurb: "Understand arrivals, departures and net migration.",
    measured: "International migration estimates, published monthly", dashboard: { to: "/migration", label: "Explore migration" },
    term: "net-migration", tone: "bg-cat-migration", wash: "bg-cat-migration/6",
  },
};
