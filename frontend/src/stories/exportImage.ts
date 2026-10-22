import type { EChartsCoreOption } from "echarts/core";
import { renderChartImage } from "@/charts/echarts";
import type { ChartTheme } from "@/charts/theme";
import { font, layoutExport, type ExportFormat, type ExportText } from "./exportLayout";

const loadImage = (src: string) =>
  new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Chart image could not be loaded"));
    image.src = src;
  });

/** Draws the story card: plain text only (no upstream HTML is interpreted), chart re-rendered at its exact size. */
export async function storyPng(
  text: ExportText, format: ExportFormat, option: EChartsCoreOption, theme: ChartTheme, accent: string,
): Promise<string> {
  // Canvas text falls back to a system font unless the web font's weights are loaded first.
  await Promise.all([400, 600].map((w) => document.fonts?.load(font(16, w)).catch(() => undefined)));
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Image export is unavailable");
  const layout = layoutExport(text, format, (t, f) => {
    ctx.font = f;
    return ctx.measureText(t).width;
  });
  canvas.width = layout.width;
  canvas.height = layout.height;
  ctx.fillStyle = theme.surface;
  ctx.fillRect(0, 0, layout.width, layout.height);
  const [bar, ...rules] = layout.rules;
  ctx.fillStyle = accent;
  ctx.fillRect(bar.x, bar.y, bar.w, bar.h);
  ctx.fillStyle = theme.grid;
  for (const r of rules) ctx.fillRect(r.x, r.y, r.w, r.h);
  const { x, y, w, h } = layout.chart;
  ctx.drawImage(await loadImage(renderChartImage(option, w, h, theme.surface, format === "portrait" ? 1.6 : 1.2)), x, y, w, h);
  ctx.textBaseline = "top";
  for (const line of layout.lines) {
    ctx.font = line.font;
    ctx.fillStyle = line.tone === "accent" ? accent : line.tone === "muted" ? theme.muted : theme.text;
    ctx.fillText(line.text, line.x, line.y);
  }
  return canvas.toDataURL("image/png");
}
