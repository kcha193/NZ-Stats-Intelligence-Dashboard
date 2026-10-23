import type { Story } from "./types";

/** Short, fixed definitions for the terms a non-specialist meets in the stories. No figures, no causal claims. */
export const GLOSSARY = {
  cpi: {
    term: "CPI inflation",
    short: "How much the prices households pay have changed.",
    body: "The consumers price index (CPI) tracks the prices of a fixed basket of goods and services bought by New Zealand households. Inflation is the percentage change in that index.",
  },
  "annual-quarterly": {
    term: "Annual and quarterly inflation",
    short: "Two different comparisons of the same index.",
    body: "Annual inflation compares a quarter with the same quarter a year earlier. Quarterly inflation compares it with the quarter before. They measure different things and are never added together.",
  },
  "inflation-falling": {
    term: "Lower inflation is not falling prices",
    short: "Prices can still rise while inflation eases.",
    body: "When annual inflation drops from, say, 5% to 3%, prices are still rising, just more slowly. Prices only fall when the inflation rate itself is below zero.",
  },
  pp: {
    term: "Percentage points",
    short: "The difference between two percentages.",
    body: "Going from 3% to 4% is a change of 1 percentage point (pp), not 1%. Percentage points are also how contributions to inflation are measured.",
  },
  contribution: {
    term: "Contribution",
    short: "One group's share of the headline change, in percentage points.",
    body: "A group's contribution combines its own price change with its weight in household spending. Contributions roughly add up to the headline inflation rate. A contribution is not the group's own price change.",
  },
  tradables: {
    term: "Tradables and non-tradables",
    short: "Prices set by world markets versus at home.",
    body: "Tradables face foreign competition (fuel, imported goods). Non-tradables do not (rents, rates, many services). Non-tradables inflation is not the same as core inflation.",
  },
  "seasonally-adjusted": {
    term: "Seasonally adjusted",
    short: "Regular calendar effects removed.",
    body: "Spending rises every December and dips in January. Seasonal adjustment removes those regular patterns so that one month can be compared with the next. Adjusted figures are re-estimated, and can change, as new months arrive.",
  },
  nominal: {
    term: "Nominal values",
    short: "Measured in dollars of the day, including price changes.",
    body: "Card spending is recorded in current dollars. Higher spending can mean higher prices, more purchases, or both.",
  },
  "net-migration": {
    term: "Net migration",
    short: "Long-term arrivals minus long-term departures.",
    body: "A traveller counts as a long-term migrant if they stay in (or out of) New Zealand for 12 of the following 16 months. A positive figure is a net gain of people, a negative one a net loss.",
  },
  "year-ended": {
    term: "Year-ended totals",
    short: "The sum of the latest twelve months.",
    body: "A year-ended figure adds up twelve months, so it moves smoothly. It is compared with the twelve months a year earlier, which do not overlap. Year-ended and single-month figures are different series.",
  },
  provisional: {
    term: "Provisional estimate",
    short: "An early estimate that will be revised.",
    body: "Recent migration months are estimated before travellers' final outcomes are known. Stats NZ revises them as the 16-month window closes.",
  },
  revisions: {
    term: "Revisions",
    short: "Earlier figures can change in later releases.",
    body: "Each release can update previously published values (new information, re-estimated seasonal patterns). Stories use one release at a time and name it; the Data health and release pages record what changed.",
  },
} as const;

export type TermKey = keyof typeof GLOSSARY;

const BY_TEMPLATE: Record<string, TermKey[]> = {
  "inflation-annual": ["cpi", "annual-quarterly", "inflation-falling", "pp"],
  "inflation-drivers": ["contribution", "pp", "annual-quarterly"],
  "inflation-tradables": ["tradables", "pp", "cpi"],
  "spending-retail": ["seasonally-adjusted", "nominal", "revisions"],
  "spending-industries": ["seasonally-adjusted", "nominal"],
  "migration-net": ["net-migration", "year-ended", "provisional"],
  "migration-flows": ["net-migration", "year-ended", "provisional"],
  "migration-citizenship": ["net-migration", "year-ended", "provisional"],
};

/** The terms a story's reader may need, most important first; provisional only when the story's data is. */
export function termsFor(story: Pick<Story, "template" | "dataStatus">): TermKey[] {
  return (BY_TEMPLATE[story.template] ?? []).filter((k) => k !== "provisional" || story.dataStatus === "provisional");
}
