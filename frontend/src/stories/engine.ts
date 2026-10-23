import { CATEGORY_LABEL, type Glance, type Story, type StoryCategory } from "./types";

/** Newest publication first; within one release, the editorial order of its templates. Ids are unique. */
export function orderStories(stories: Story[]): Story[] {
  const seen = new Set<string>();
  return [...stories]
    .sort((a, b) =>
      Date.parse(b.provenance.publishedAt) - Date.parse(a.provenance.publishedAt) || a.priority - b.priority)
    .filter((s) => !seen.has(s.id) && Boolean(seen.add(s.id)));
}

export function splitTemplate(id: string): { template: string; period: string } | null {
  const m = /^([a-z]+(?:-[a-z]+)*)-(\d{4}-\d{2})$/.exec(id);
  return m ? { template: m[1], period: m[2] } : null;
}

/** Ids are `<template>-<period>` and every template is named for its category, so the id says which source must load. */
export function categoryOfId(id: string): StoryCategory | null {
  const category = splitTemplate(id)?.template.split("-")[0] ?? "";
  return category in CATEGORY_LABEL ? (category as StoryCategory) : null;
}

export type Resolution =
  | { kind: "found"; story: Story }
  | { kind: "superseded"; requested: string; current: Story }
  | { kind: "missing" };

/** An older period of a template the data now covers more recently is "superseded", never re-pointed silently. */
export function resolveStory(stories: Story[], id: string): Resolution {
  const story = stories.find((s) => s.id === id);
  if (story) return { kind: "found", story };
  const parts = splitTemplate(id);
  const current = parts && stories.find((s) => s.template === parts.template);
  if (parts && current && parts.period < current.referencePeriod) {
    return { kind: "superseded", requested: parts.period, current };
  }
  return { kind: "missing" };
}

/** The reading order of the homepage's headline measures: prices, then spending, then people. */
export const GLANCE_ORDER: StoryCategory[] = ["inflation", "spending", "migration"];

/** One headline measure per category, from the first (newest) story in that category that carries one. */
export function glanceStories(stories: Story[]): (Story & { glance: Glance })[] {
  return GLANCE_ORDER.flatMap((c) => {
    const s = stories.find((x) => x.category === c && x.glance);
    return s ? [s as Story & { glance: Glance }] : [];
  });
}

export type Collection = { prominent: Story | undefined; supporting: Story[]; rest: Story[] };

/**
 * The story collection under the lead: one prominent story, two supporting stories, then the rest. Picks avoid
 * repeating a category already on show where another is available, so the page does not open with three stories on one
 * topic; within each slot, newer stories still come first. Nothing is invented when there are fewer stories.
 */
export function arrangeCollection(lead: Story, rest: Story[]): Collection {
  const used = new Set<StoryCategory>([lead.category]);
  const prominent = rest.find((s) => !used.has(s.category)) ?? rest[0];
  if (prominent) used.add(prominent.category);
  const pool = rest.filter((s) => s !== prominent);
  const picked = new Set<Story>();
  for (const s of pool) {
    if (picked.size === 2) break;
    if (!used.has(s.category)) {
      picked.add(s);
      used.add(s.category);
    }
  }
  for (const s of pool) if (picked.size < 2) picked.add(s);
  return {
    prominent,
    supporting: pool.filter((s) => picked.has(s)),
    rest: pool.filter((s) => !picked.has(s)),
  };
}

/** Stories to read next: the same topic first, then the rest, each in feed (newest first) order. */
export function relatedStories(stories: Story[], story: Story, max: number): Story[] {
  const others = stories.filter((s) => s.id !== story.id);
  return [...others.filter((s) => s.category === story.category), ...others.filter((s) => s.category !== story.category)].slice(0, max);
}

/** The stories either side of one in the feed. */
export function neighbours(stories: Story[], id: string): { previous: Story | undefined; next: Story | undefined } {
  const i = stories.findIndex((s) => s.id === id);
  return i < 0 ? { previous: undefined, next: undefined } : { previous: stories[i - 1], next: stories[i + 1] };
}
