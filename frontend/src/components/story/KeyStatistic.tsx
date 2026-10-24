import type { KeyStat } from "@/stories/types";

const SIZE = {
  xl: { value: "text-6xl sm:text-7xl lg:text-[5.5rem]", unit: "text-sm" },
  lg: { value: "text-5xl sm:text-6xl", unit: "text-sm" },
  md: { value: "text-3xl", unit: "text-xs" },
} as const;

/** The story's one number, with its unit always beside it. Colour never carries the sign: the text does. */
export function KeyStatistic({ stat, size = "lg" }: { stat: KeyStat; size?: keyof typeof SIZE }) {
  return (
    <div role="group" aria-label="Key statistic" className="min-w-0">
      <p className={`type-figure ${SIZE[size].value}`}>{stat.value}</p>
      <p className={`mt-3 font-medium ${SIZE[size].unit}`}>{stat.unit}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{stat.label}</p>
    </div>
  );
}
