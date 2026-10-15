import type { Insight } from "@/api/types";
import { Badge } from "@/components/ui/badge";

export function InsightList({ insights }: { insights: Insight[] }) {
  return (
    <ol className="space-y-3">
      {insights.map((i) => (
        <li key={i.id} className="text-sm leading-relaxed">
          <p>
            {i.kind === "inference" && (
              <Badge variant="outline" className="mr-2 align-middle">Inference</Badge>
            )}
            {i.text}
          </p>
          {i.caveat && <p className="mt-0.5 text-xs text-muted-foreground">{i.caveat}</p>}
          <details className="mt-0.5 text-xs text-muted-foreground">
            <summary className="cursor-pointer">Evidence ({i.evidence.length})</summary>
            <ul className="mt-1 list-disc pl-5">
              {i.evidence.map((e, n) => (
                <li key={n}>{e.series_key} · {e.period} · {e.value.toLocaleString("en-NZ")} · {e.release_key}</li>
              ))}
            </ul>
          </details>
        </li>
      ))}
    </ol>
  );
}
