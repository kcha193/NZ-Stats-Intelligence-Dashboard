import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import type { EChartsCoreOption } from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import {
  AriaComponent, AxisPointerComponent, GridComponent, LegendComponent, MarkAreaComponent,
  MarkLineComponent, MarkPointComponent, TitleComponent, TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, MarkPointComponent,
  MarkAreaComponent, MarkLineComponent, TitleComponent, AriaComponent, AxisPointerComponent,
  CanvasRenderer,
]);

export type ChartInstance = echarts.ECharts;

export function EChart({
  option, ariaLabel, height = 320, onReady,
}: {
  option: EChartsCoreOption;
  ariaLabel: string;
  height?: number;
  onReady?: (chart: ChartInstance) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<ChartInstance | null>(null);
  const ready = useRef(onReady);

  useEffect(() => {
    ready.current = onReady;
  });

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const instance = echarts.init(el, undefined, { renderer: "canvas" });
    chart.current = instance;
    ready.current?.(instance);
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true });
  }, [option]);

  return <div ref={host} role="img" aria-label={ariaLabel} style={{ height }} className="w-full" />;
}
