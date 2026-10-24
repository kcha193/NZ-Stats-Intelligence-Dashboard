import { useSearchParams } from "react-router-dom";
import { isStaticMode } from "@/api/mode";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";
import { Segmented } from "@/components/Segmented";
import { QueryBoundary } from "@/components/QueryBoundary";
import { StoryGrid } from "@/components/story/StoryCard";
import { CATEGORY_LABEL, type StoryCategory } from "@/stories/types";
import { useStories, type SourceState } from "@/stories/useStories";

const CATEGORIES = Object.keys(CATEGORY_LABEL) as StoryCategory[];
const REASON: Record<Exclude<SourceState, "ready" | "loading">, string> = {
  not_ingested: isStaticMode() ? "no data has been published yet" : "no data has been ingested yet",
  error: "the data could not be loaded",
};

export default function Stories() {
  useDocumentTitle(ROUTE_META["/stories"].title);
  const [params, setParams] = useSearchParams();
  const requested = params.get("category");
  const category = CATEGORIES.includes(requested as StoryCategory) ? (requested as StoryCategory) : "all";
  const { stories, sources, isLoading: anyLoading } = useStories();
  const pending = CATEGORIES.filter((c) => sources[c] === "loading");
  // Nothing to show yet: the requested category is still loading, or (for all) no category has produced a story.
  const isLoading = category === "all" ? anyLoading && stories.length === 0 : sources[category] === "loading";
  const shown = category === "all" ? stories : stories.filter((s) => s.category === category);
  const missing = CATEGORIES.filter((c) => sources[c] === "not_ingested" || sources[c] === "error");
  const options = [
    { value: "all", label: `All (${stories.length})` },
    ...CATEGORIES.map((c) => ({ value: c, label: `${CATEGORY_LABEL[c]} (${stories.filter((s) => s.category === c).length})` })),
  ];
  return (
    <div className="space-y-8">
      <header className="max-w-[70ch] border-b-2 border-rule-strong pb-6">
        <p className="kicker">Visual stories</p>
        <h1 className="type-masthead mt-2">Stories</h1>
        <p className="mt-3 text-lg leading-relaxed text-muted-foreground">
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
      {!isLoading && pending.length > 0 && (
        <p role="status" className="text-xs text-muted-foreground">Still loading: {pending.map((c) => CATEGORY_LABEL[c]).join(", ")}.</p>
      )}
      {!isLoading && missing.length > 0 && (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {missing.map((c) => (
            <li key={c}>{CATEGORY_LABEL[c]}: {REASON[sources[c] as "not_ingested" | "error"]}, so it has no stories. {isStaticMode() ? "Data health shows what this site has published." : "Check Data health for ingestion status."}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
