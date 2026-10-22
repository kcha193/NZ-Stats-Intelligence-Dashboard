import { useSearchParams } from "react-router-dom";
import { Segmented } from "@/components/Segmented";
import { QueryBoundary } from "@/components/QueryBoundary";
import { StoryGrid } from "@/components/story/StoryCard";
import { CATEGORY_LABEL, type StoryCategory } from "@/stories/types";
import { useStories, type SourceState } from "@/stories/useStories";

const CATEGORIES = Object.keys(CATEGORY_LABEL) as StoryCategory[];
const REASON: Record<Exclude<SourceState, "ready" | "loading">, string> = {
  not_ingested: "no data has been ingested yet",
  error: "the data could not be loaded",
};

export default function Stories() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("category");
  const category = CATEGORIES.includes(requested as StoryCategory) ? (requested as StoryCategory) : "all";
  const { stories, sources, isLoading } = useStories();
  const shown = category === "all" ? stories : stories.filter((s) => s.category === category);
  const missing = CATEGORIES.filter((c) => sources[c] === "not_ingested" || sources[c] === "error");
  const options = [
    { value: "all", label: `All (${stories.length})` },
    ...CATEGORIES.map((c) => ({ value: c, label: `${CATEGORY_LABEL[c]} (${stories.filter((s) => s.category === c).length})` })),
  ];
  return (
    <div className="space-y-6">
      <header className="max-w-[70ch]">
        <p className="kicker">Visual stories</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Stories</h1>
        <p className="mt-2 text-base text-muted-foreground">
          One finding per story, drawn from the latest verified Stats NZ release. Each story names its reference period,
          publication date and source, and links to the full dashboard.
        </p>
      </header>
      <div className="overflow-x-auto pb-1">
        <Segmented label="Story category" value={category} options={options}
          onChange={(v) => setParams(v === "all" ? {} : { category: v }, { replace: true })} />
      </div>
      <QueryBoundary query={{ data: isLoading ? undefined : stories, error: null, isLoading, isError: false, refetch: () => undefined }}>
        {() => shown.length
          ? <StoryGrid stories={shown} label={category === "all" ? "All stories" : `${CATEGORY_LABEL[category]} stories`} />
          : <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              {category === "all" ? "No stories are available yet." : `No ${CATEGORY_LABEL[category].toLowerCase()} stories are available.`}
            </p>}
      </QueryBoundary>
      {!isLoading && missing.length > 0 && (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {missing.map((c) => (
            <li key={c}>{CATEGORY_LABEL[c]}: {REASON[sources[c] as "not_ingested" | "error"]}, so it has no stories. Check Data health for ingestion status.</li>
          ))}
        </ul>
      )}
    </div>
  );
}
