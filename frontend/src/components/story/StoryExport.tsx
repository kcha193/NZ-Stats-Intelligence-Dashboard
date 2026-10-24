import { useState } from "react";
import { ImageDown, Link as LinkIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ChartTheme } from "@/charts/theme";
import { saveFile } from "@/lib/download";
import { absoluteUrl } from "@/lib/siteUrl";
import { exportText, FORMATS, type ExportFormat } from "@/stories/exportLayout";
import { storyPng } from "@/stories/exportImage";
import type { FigureView } from "@/stories/figures";
import type { Story } from "@/stories/types";

const accentInk = () =>
  getComputedStyle(document.documentElement).getPropertyValue("--accent-ink").trim() || "#2b66a8";

/** Presentation PNGs of exactly what the page shows (same option, same values), plus a share link. */
export function StoryExport({ story, view, theme }: { story: Story; view: FigureView; theme: ChartTheme }) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const storyUrl = absoluteUrl(`/stories/${story.id}`);

  const exportPng = async (format: ExportFormat) => {
    setBusy(true);
    setStatus("");
    try {
      const text = exportText(story, view, storyUrl);
      saveFile(await storyPng(text, format, view.option, theme, accentInk()), `${story.id}-${format}.png`);
      setStatus(`${FORMATS[format].label} exported with source, publication date and reference period.`);
    } catch {
      setStatus("Image export failed. Please try again.");
    } finally {
      setBusy(false);
    }
  };
  const share = async () => {
    try {
      if (navigator.share) {
        await navigator.share({ title: story.headline, text: story.dek, url: storyUrl });
        return;
      }
      await navigator.clipboard.writeText(storyUrl);
      setStatus("Link copied.");
    } catch (e) {
      if ((e as Error).name !== "AbortError") setStatus(`Copy this link: ${storyUrl}`);
    }
  };

  return (
    <div className="space-y-1 print:hidden">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Export and share">
        {(Object.keys(FORMATS) as ExportFormat[]).map((f) => (
          <Button key={f} variant="outline" size="sm" disabled={busy} onClick={() => void exportPng(f)}>
            <ImageDown aria-hidden /> {FORMATS[f].label}
          </Button>
        ))}
        <Button variant="outline" size="sm" onClick={() => void share()}>
          <LinkIcon aria-hidden /> Share link
        </Button>
      </div>
      <p role="status" className="text-xs text-muted-foreground">{status}</p>
    </div>
  );
}
