import type { ChartTheme } from "./theme";

/** Append a plain-text, wrapped caption to ECharts' bitmap. No upstream HTML is interpreted. */
export async function captionedChartPng(
  chartUrl: string, paragraphs: string[], theme: ChartTheme,
): Promise<string> {
  const image = new Image();
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error("Chart image could not be loaded"));
    image.src = chartUrl;
  });
  const ratio = 2; // matches ChartCard's ECharts pixelRatio
  const padding = 16;
  const lineHeight = 20;
  // Narrow mobile charts still need room for a readable source URL and caption.
  const width = Math.max(image.width / ratio, 320);
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Image export is unavailable");
  ctx.font = "14px sans-serif";
  const lines: string[] = [];
  for (const paragraph of paragraphs) {
    let line = "";
    // Split long tokens (notably URLs), preserving every character. Prefer whitespace breaks.
    for (const char of paragraph.replace(/\s+/g, " ")) {
      if (ctx.measureText(line + char).width > width - padding * 2 && line) {
        const space = line.lastIndexOf(" ");
        if (space > 0) {
          lines.push(line.slice(0, space));
          line = line.slice(space + 1) + char;
        } else {
          lines.push(line);
          line = char;
        }
      } else line += char;
    }
    if (line) lines.push(line);
  }
  const chartHeight = image.height / ratio;
  canvas.width = Math.ceil(width * ratio);
  canvas.height = Math.ceil((chartHeight + padding * 2 + lines.length * lineHeight) * ratio);
  ctx.scale(ratio, ratio);
  ctx.fillStyle = theme.surface;
  ctx.fillRect(0, 0, width, canvas.height / ratio);
  ctx.drawImage(image, 0, 0, image.width / ratio, chartHeight);
  // Setting dimensions resets the context, so restore the caption style after resizing.
  ctx.font = "14px sans-serif";
  ctx.fillStyle = theme.text;
  ctx.textBaseline = "top";
  lines.forEach((line, index) =>
    ctx.fillText(line, padding, chartHeight + padding + index * lineHeight),
  );
  return canvas.toDataURL("image/png");
}
