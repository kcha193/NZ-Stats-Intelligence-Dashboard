import type { Story } from "./types";

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
