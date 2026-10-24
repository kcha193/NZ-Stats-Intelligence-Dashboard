/** Page titles and descriptions: one table for the running app and for the build-time page metadata. */

export const SITE_NAME = "NZ Stats Intelligence";

export type PageMeta = { title: string; description: string };

export const ROUTE_META: Record<string, PageMeta> = {
  "/": {
    title: "New Zealand's economy, explained",
    description:
      "Prices, card spending and migration explained from official Stats NZ releases, with the published figures, definitions and sources behind every chart.",
  },
  "/stories": {
    title: "Stories",
    description: "Every finding from the latest Stats NZ releases on inflation, card spending and migration, one story per page.",
  },
  "/inflation": {
    title: "Inflation: consumers price index",
    description: "Quarterly consumers price index from Stats NZ: annual and quarterly change, what drove it, and tradables versus non-tradables.",
  },
  "/electronic-card-transactions": {
    title: "Card spending: electronic card transactions",
    description: "Monthly electronic card transactions from Stats NZ: retail spending, industries and how the figures are revised.",
  },
  "/migration": {
    title: "Migration: arrivals and departures",
    description: "Monthly and year-ended international migration from Stats NZ: net migration, arrivals, departures, citizenship and countries.",
  },
  "/calendar": {
    title: "Release calendar",
    description: "Scheduled and recently published Stats NZ releases, with the ones this site has verified marked.",
  },
  "/health": {
    title: "Data health",
    description: "When each Stats NZ source was last checked and last succeeded, and how many releases and series this snapshot holds.",
  },
};

export const withSiteName = (title: string): string => (title.includes(SITE_NAME) ? title : `${title} | ${SITE_NAME}`);

export function metaFor(pathname: string): PageMeta | undefined {
  return ROUTE_META[pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname];
}
