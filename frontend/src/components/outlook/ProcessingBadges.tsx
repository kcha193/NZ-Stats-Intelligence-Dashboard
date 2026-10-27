import { BadgeCheck, Bot, FileCheck2, UserCheck } from "lucide-react";
import type { ResearchItem } from "@/api/types";
import { formatCivilDate } from "@/lib/format";

/**
 * How a summary got here, in order: written by a model, checked against the document, reviewed by a person, then
 * approved for publication. Each step is a word and an icon, never colour alone.
 */
export function ProcessingBadges({ item }: { item: ResearchItem }) {
  const p = item.processing;
  const steps = [
    { icon: Bot, label: "AI summary" },
    { icon: FileCheck2, label: "Evidence checked" },
    { icon: UserCheck, label: `Human reviewed ${formatCivilDate(p.human_reviewed_on)}` },
    { icon: BadgeCheck, label: `Published here ${formatCivilDate(p.published_here_on)}` },
  ];
  return (
    <ul aria-label="Processing and review" className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {steps.map(({ icon: Icon, label }) => (
        <li key={label} className="inline-flex items-center gap-1">
          <Icon aria-hidden className="size-3.5 text-accent-ink" strokeWidth={1.75} />
          {label}
        </li>
      ))}
    </ul>
  );
}
