import { Badge } from "@/components/ui/badge";

const LABEL: Record<string, string> = {
  provisional: "Provisional", final: "Final", unknown: "Status n/a",
  scheduled: "Scheduled", published: "Published", delayed: "Delayed",
  corrected: "Corrected", unavailable: "Unavailable",
};

export function StatusBadge({ status }: { status: string }) {
  const emphasised = ["provisional", "delayed", "corrected", "unavailable"].includes(status);
  return (
    <Badge variant={emphasised ? "outline" : "secondary"} className={emphasised ? "border-amber-600/60 text-amber-800 dark:text-amber-300" : ""}>
      {LABEL[status] ?? status}
    </Badge>
  );
}
