import type { EChartsCoreOption } from 'echarts/core';
import { escapeHtml, formatNumber, monthLabel } from '@/lib/format';
import { lineOption, monthAxis, rankedBarOption, type ChartPoint } from './options';
import type { ChartTheme } from './theme';

export type HistoryScale='zoomed'|'zero';

/** Padded axis bounds for a level series: contains every value and is never below zero. */
export function zoomedRange(points:ChartPoint[]): {min:number;max:number} {
  const values=points.map(p=>p.value);
  const lo=Math.min(...values),hi=Math.max(...values);
  const span=hi-lo||Math.abs(hi)*0.02||1;
  const step=10**Math.floor(Math.log10(span))/2;
  return {min:Math.max(0,Math.floor((lo-span*0.25)/step)*step),max:Math.ceil((hi+span*0.25)/step)*step};
}

export function ectHistoryOption(input: {name:string;points:ChartPoint[];frequency:string}, theme:ChartTheme, scale:HistoryScale='zero'): EChartsCoreOption {
  const base=lineOption({series:[{name:input.name,points:input.points,color:theme.series[0]}],unit:'NZD million',frequency:'monthly'},theme);
  const quarterly=input.frequency==='quarterly';
  const periods=monthAxis(input.points.map(p=>p.period)).filter(p=>!quarterly || /-(03|06|09|12)$/.test(p));
  const byPeriod=new Map(input.points.map(p=>[p.period,p]));
  const zoomed=scale==='zoomed' && input.points.length>0;
  const range=zoomed?zoomedRange(input.points):null;
  const decimals=range && range.max-range.min<1500?2:1;
  const billions=(v:number,d=decimals)=>`$${formatNumber(v/1000,{decimals:d})}b`;
  return {...base,
    ...(range?{title:{text:`Axis starts at ${billions(range.min,2)} (not zero)`,left:0,top:0,
      textStyle:{fontSize:11,fontWeight:'normal',color:theme.muted}},grid:{...(base.grid as object),top:32}}:{}),
    xAxis:{...(base.xAxis as object),data:periods,axisLabel:{interval:0,color:theme.muted,hideOverlap:true,
      formatter:(p:string)=>p.endsWith(quarterly?'-03':'-01')?p.slice(0,4):''}},
    yAxis:{...(base.yAxis as object),...(range?{min:range.min,max:range.max}:{min:0}),axisLabel:{color:theme.muted,formatter:(v:number)=>billions(v)}},
    tooltip:{trigger:'axis',formatter:(params:{axisValue:string;value:number|null}[])=>{
      const p=String(params[0]?.axisValue ?? '');const point=byPeriod.get(p);
      return `${quarterly?'Quarter ended ':''}${monthLabel(p)}<br/>${escapeHtml(input.name)}: <b>${point?formatNumber(point.value,{decimals:1}):'Missing'}</b> NZD million${point?.status==='provisional'?' (provisional)':point?.status==='unknown'?' (revised / status unknown)':''}`;
    }},
    series:[{...((base.series as object[])[0]),data:periods.map(p=>byPeriod.get(p)?.value ?? null)}],
  };
}

export function ectIndustryOption(items:{name:string;value:number}[],theme:ChartTheme,unit:'percent'|'NZD million'): EChartsCoreOption {
  const sorted=[...items].sort((a,b)=>b.value-a.value);
  const base=rankedBarOption({items:sorted.map(i=>({...i,provisional:false})),unit},theme);
  const floor=unit==='percent'?Math.floor(Math.min(0,...items.map(i=>i.value))*1.2):Math.min(0,...items.map(i=>i.value))*1.2;
  return {...base,grid:{left:4,right:64,top:12,bottom:30,containLabel:true},
    yAxis:{...(base.yAxis as object),axisLabel:{color:theme.text,width:110,overflow:'break'}},
    xAxis:{...(base.xAxis as object),min:floor,splitNumber:4,
      axisLabel:{color:theme.muted,hideOverlap:true,formatter:(v:number)=>`${formatNumber(v,{decimals:unit==='percent'?1:0})}${unit==='percent'?'%':''}`}},
    tooltip:{trigger:'item',formatter:(p:{name:string;value:number})=>
      `${escapeHtml(p.name)}: <b>${formatNumber(p.value,{signed:unit==='percent',decimals:1})}</b> ${unit==='percent'?'%':unit}`},
    series:[{...((base.series as object[])[0]),
      label:{show:true,position:'right',color:theme.text,formatter:(p:{value:number})=>`${formatNumber(p.value,{signed:unit==='percent',decimals:1})}${unit==='percent'?'%':''}`},
      markLine:{silent:true,symbol:'none',label:{show:false},lineStyle:{color:theme.muted},data:[{xAxis:0}]},
      data:sorted.map(i=>({name:i.name,value:i.value,itemStyle:{color:unit==='NZD million'?theme.series[0]:i.value<0?theme.negative:theme.positive}}))}],
  };
}
