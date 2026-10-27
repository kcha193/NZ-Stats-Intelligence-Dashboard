import * as echarts from "echarts/core";
import type { EChartsCoreOption } from "echarts/core";
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  AriaComponent, AxisPointerComponent, GridComponent, LegendComponent, MarkAreaComponent,
  MarkLineComponent, MarkPointComponent, TitleComponent, TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart, BarChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, MarkPointComponent,
  MarkAreaComponent, MarkLineComponent, TitleComponent, AriaComponent, AxisPointerComponent,
  CanvasRenderer,
]);

export { echarts };

/** Renders an option off-screen for image export: laid out at width/scale and drawn at `scale`, so the bitmap is
 * exactly width × height and every label, axis and annotation is enlarged together for presentation. */
export function renderChartImage(option: EChartsCoreOption, width: number, height: number, background: string, scale = 1): string {
  const el = document.createElement("div");
  const instance = echarts.init(el, undefined, { renderer: "canvas", width: width / scale, height: height / scale });
  try {
    instance.setOption({ ...option, animation: false });
    return instance.getDataURL({ type: "png", pixelRatio: scale, backgroundColor: background });
  } finally {
    instance.dispose();
  }
}
