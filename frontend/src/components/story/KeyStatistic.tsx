import type { KeyStat } from "@/stories/types";

/** The story's one number, with its unit always beside it. Colour never carries the sign: the text does. */
export function KeyStatistic({ stat, size = "lg" }: { stat: KeyStat; size?: "lg" | "md" }) {
  return (
    <div role="group" aria-label="Key statistic" className="min-w-0">
      <p className={`whitespace-nowrap font-semibold leading-none tracking-tight tabular-nums ${size === "lg" ? "text-5xl sm:text-6xl" : "text-3xl"}`}>
        {stat.value}
      </p>
      <p className={`mt-2 font-medium ${size === "lg" ? "text-sm" : "text-xs"}`}>{stat.unit}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{stat.label}</p>
    </div>
  );
}
