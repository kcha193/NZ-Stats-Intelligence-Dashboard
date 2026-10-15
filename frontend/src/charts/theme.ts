import { useEffect, useState } from "react";

export type ChartTheme = {
  text: string; muted: string; grid: string; surface: string;
  series: string[]; positive: string; negative: string;
  provisionalBand: string; provisionalBar: string;
};

export const TEST_THEME: ChartTheme = {
  text: "#111", muted: "#666", grid: "#ddd", surface: "#fff",
  series: ["#2b66a8", "#c75f0c", "#2a8a6c", "#7b52b5"],
  positive: "#2f6f5e", negative: "#a23b3b",
  provisionalBand: "rgba(180,101,26,0.10)", provisionalBar: "#8fb0cc",
};

export function readTheme(): ChartTheme {
  const s = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => s.getPropertyValue(name).trim() || fallback;
  return {
    text: v("--chart-text", TEST_THEME.text),
    muted: v("--chart-muted", TEST_THEME.muted),
    grid: v("--chart-grid", TEST_THEME.grid),
    surface: v("--chart-surface", TEST_THEME.surface),
    series: [1, 2, 3, 4].map((i) => v(`--chart-${i}`, TEST_THEME.series[i - 1])),
    positive: v("--chart-positive", TEST_THEME.positive),
    negative: v("--chart-negative", TEST_THEME.negative),
    provisionalBand: v("--chart-provisional-band", TEST_THEME.provisionalBand),
    provisionalBar: v("--chart-provisional-bar", TEST_THEME.provisionalBar),
  };
}

export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState<ChartTheme>(() => readTheme());
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setTheme(readTheme());
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return theme;
}
