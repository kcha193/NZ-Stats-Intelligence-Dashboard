import { useMemo } from "react";
import { ApiError } from "@/api/client";
import { useCpi } from "@/api/hooks";
import { buildCpiStories } from "./cpi";
import { orderStories } from "./engine";
import type { Story, StoryCategory } from "./types";

export type SourceState = "ready" | "loading" | "not_ingested" | "error";

type Q<T> = { data: T | undefined; error: Error | null; isLoading: boolean };

const stateOf = (qs: Q<unknown>[]): SourceState => {
  if (qs.some((q) => q.isLoading)) return "loading";
  if (qs.some((q) => q.error instanceof ApiError && q.error.status === 404)) return "not_ingested";
  if (qs.some((q) => q.error)) return "error";
  return "ready";
};

/** Every story the ingested data supports, plus why a category has none. Categories load independently. */
export function useStories(): { stories: Story[]; sources: Record<StoryCategory, SourceState>; isLoading: boolean } {
  const cpi = useCpi();
  return useMemo(() => {
    const sources: Record<StoryCategory, SourceState> = {
      inflation: stateOf([cpi]), spending: "not_ingested", migration: "not_ingested",
    };
    const stories = orderStories([...(cpi.data ? buildCpiStories(cpi.data) : [])]);
    return { stories, sources, isLoading: Object.values(sources).includes("loading") };
  }, [cpi]);
}
