import { useState } from 'react';
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";
import { Link } from 'react-router-dom';
import { ApiError } from '@/api/client';
import { useEct } from '@/api/hooks';
import { isStaticMode } from '@/api/mode';
import type { EctDashboard, SeriesData } from '@/api/types';
import { ChartCard } from '@/charts/ChartCard';
import { ectHistoryOption, ectIndustryOption, zoomedRange, type HistoryScale } from '@/charts/ect';
import { sliceYears } from '@/charts/options';
import { useChartTheme } from '@/charts/theme';
import { InsightList } from '@/components/InsightList';
import { EmptyState, QueryBoundary } from '@/components/QueryBoundary';
import { Segmented } from '@/components/Segmented';
import { formatAklDateTime, formatNumber, formatPercent, monthLabel } from '@/lib/format';

const INDUSTRIES=[['consumables','Consumables'],['durables','Durables'],['hospitality','Hospitality'],
  ['apparel','Apparel'],['motor_vehicles','Motor vehicles excl. fuel'],['fuel','Fuel'],
  ['services','Services'],['non_retail','Non-retail excl. services']];
const ADJUSTMENTS={actual:'Actual',sa:'Seasonally adjusted',trend:'Trend'};
function priorPeriod(period:string,lag:number):string {
  const [year,month]=period.split('-').map(Number);const n=year*12+month-1-lag;
  return `${Math.floor(n/12)}-${String(n%12+1).padStart(2,'0')}`;
}

function Dashboard({data}:{data:EctDashboard}) {
  const [group,setGroup]=useState('retail');
  const [adjustment,setAdjustment]=useState<keyof typeof ADJUSTMENTS>('sa');
  const [requestedFrequency,setFrequency]=useState('m');
  const [window,setWindow]=useState('3');
  const [scale,setScale]=useState<HistoryScale>('zoomed');
  const theme=useChartTheme();const a=data.analysis;const rel=a.release;
  const series=new Map(data.series.map(s=>[s.series.key,s]));
  const quarterly=series.has(`ect.q.${adjustment}.${group}.value`);
  const frequency=requestedFrequency==='q' && quarterly?'q':'m';
  const selected=series.get(`ect.${frequency}.${adjustment}.${group}.value`);
  const points=selected?sliceYears(selected.points,window==='full'?null:Number(window)):[];
  const axisMin=scale==='zoomed' && points.length?zoomedRange(points).min:null;
  const metrics=new Map(a.headline_metrics.map(m=>[m.series_key,m]));
  const retail=metrics.get('ect.m.sa.retail.value')!;const core=metrics.get('ect.m.sa.core.value')!;
  const total=metrics.get('ect.m.actual.total.value')!;
  const period=(p:string)=>`${frequency==='q'?'Quarter ended ':''}${monthLabel(p)}`;
  const last=selected?.points.at(-1);
  const source={label:`Stats NZ, ${rel.title}`,url:rel.page_url,updated:rel.published_at,captured:a.vintage_captured_at};
  const industries=INDUSTRIES.flatMap(([key,name])=>{
    const s=series.get(`ect.${frequency}.sa.${key}.value`);const latest=s?.points.at(-1);
    if(!s || !latest) return [];
    const previous=s.points.find(p=>p.period===priorPeriod(latest.period,frequency==='q'?3:1));
    return previous && previous.value>0?[{name,value:(latest.value/previous.value-1)*100,period:latest.period,
      previous_period:previous.period,current:latest.value,previous:previous.value,series_key:s.series.key}]:[];
  });
  const composition=INDUSTRIES.flatMap(([key,name])=>{
    const s=series.get(`ect.${frequency}.actual.${key}.value`);const p=s?.points.at(-1);
    return s && p?[{name,value:p.value,period:p.period,series_key:s.series.key}]:[];
  });
  const exportRows=(s:SeriesData)=>points.map(p=>({period:p.period,value:p.value,unit:s.series.unit,
    frequency:s.series.frequency,adjustment:s.series.adjustment,status:p.status,series_key:s.series.key,
    release_key:s.vintage.release_key,source_url:s.source_url ?? ''}));
  const kpis=[['Retail spending · seasonally adjusted',`${formatNumber(retail.value/1000,{decimals:2})}b`,'NZD'],
    ['Retail monthly change',formatPercent(retail.change_prior?.percent),'Seasonally adjusted'],
    ['Core retail monthly change',formatPercent(core.change_prior?.percent),'Seasonally adjusted'],
    ['Total spending · actual',`${formatNumber(total.value/1000,{decimals:2})}b`,'NZD · unadjusted']];
  return <div className="space-y-5">
    <header>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Retail and spending</p>
      <h1 className="text-xl font-semibold tracking-tight">Electronic card transactions</h1>
      <p className="mt-1 text-sm text-muted-foreground">Latest reference period: {retail.period_label} · Published {formatAklDateTime(rel.published_at)}</p>
    </header>
    <section aria-label="ECT key indicators" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {kpis.map(([label,value,unit])=><article key={label} className="rounded-md border bg-card p-3">
        <h2 className="text-xs font-medium text-muted-foreground">{label}</h2>
        <p className="mt-1 text-2xl font-semibold tracking-tight">{value} <span className="text-xs font-normal text-muted-foreground">{unit}</span></p>
        <p className="mt-1 text-xs text-muted-foreground">{retail.period_label}</p>
      </article>)}
    </section>
    <section aria-label="Historical spending" className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-xs">Spending group<select className="rounded-md border bg-background px-2 py-1.5 text-sm" value={group} onChange={e=>setGroup(e.target.value)}>
          <option value="retail">Retail</option><option value="core">Core retail</option><option value="total">Total ECT</option></select></label>
        <label className="grid gap-1 text-xs">Adjustment<select className="rounded-md border bg-background px-2 py-1.5 text-sm" value={adjustment} onChange={e=>setAdjustment(e.target.value as keyof typeof ADJUSTMENTS)}>
          {Object.entries(ADJUSTMENTS).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label>
        <Segmented label="ECT frequency" value={frequency} onChange={setFrequency} options={[{value:'m',label:'Monthly'},...(quarterly?[{value:'q',label:'Quarterly'}]:[])]} />
        <Segmented label="History window" value={window} onChange={setWindow} options={[
          ...[1,3,5].filter(n=>selected && selected.points.length>=(frequency==='q'?4:12)*n).map(n=>({value:String(n),label:`${n} ${n===1?'year':'years'}`})),{value:'full',label:'Full history'}]} />
        <Segmented label="Vertical scale" value={scale} onChange={v=>setScale(v as HistoryScale)} options={[{value:'zoomed',label:'Zoomed'},{value:'zero',label:'From zero'}]} />
      </div>
      {!quarterly && <p className="text-sm text-muted-foreground">Quarterly data is not available for this selection.</p>}
      {selected?<ChartCard title={`${group==='core'?'Core retail':group==='total'?'Total ECT':'Retail'} spending · ${ADJUSTMENTS[adjustment]} · ${frequency==='q'?'quarterly':'monthly'}`}
        question={last?`${period(last.period)}: ${formatNumber(last.value,{decimals:1})} NZD million. How has spending changed over time?`:'How has spending changed over time?'}
        unit="NZD million" source={source} caveat={`${axisMin!==null?`Vertical axis starts at $${formatNumber(axisMin/1000,{decimals:2})}b, not zero. `:''}Nominal values include price changes. Seasonal and trend estimates may be revised. Quarterly data is published separately by Stats NZ.`}
        option={ectHistoryOption({name:`${group==='core'?'Core retail':group==='total'?'Total ECT':'Retail'}, ${ADJUSTMENTS[adjustment]}`,points,frequency:selected.series.frequency},theme,scale)}
        ariaLabel="ECT spending history" csvFilename="ect-spending-history.csv" csvRows={exportRows(selected)} />:
        <EmptyState title="Series unavailable" body="This release does not contain the selected series." />}
    </section>
    <div className="grid min-w-0 gap-5 xl:grid-cols-2">
      <ChartCard title={`Industry performance · ${frequency==='q'?'quarterly':'monthly'} change`}
        question={`${industries[0]?period(industries[0].period):''}: which industries moved most? Seasonally adjusted.`}
        unit="percent" source={source} caveat="Changes compare adjacent published periods within the same release vintage. Independently adjusted components need not sum to totals."
        option={ectIndustryOption(industries,theme,'percent')} ariaLabel="ECT industry movements" height={340}
        csvFilename="ect-industry-movements.csv" csvRows={industries.map(i=>({...i,unit:'percent',frequency:frequency==='q'?'quarterly':'monthly',adjustment:'seasonally_adjusted',release_key:rel.release_key,source_url:rel.page_url ?? ''}))} />
      <ChartCard title={`Spending composition · actual · ${frequency==='q'?'quarterly':'monthly'}`}
        question={`${composition[0]?period(composition[0].period):''}: where was card spending recorded?`}
        unit="NZD million" source={source} caveat="Actual industry levels are shown separately. Overlapping retail, core retail and total aggregates are excluded. These are not seasonally adjusted movements."
        option={ectIndustryOption(composition,theme,'NZD million')} ariaLabel="ECT actual spending composition" height={340}
        csvFilename="ect-actual-composition.csv" csvRows={composition.map(i=>({...i,unit:'NZD million',frequency:frequency==='q'?'quarterly':'monthly',adjustment:'none',release_key:rel.release_key,source_url:rel.page_url ?? ''}))} />
    </div>
    <section aria-labelledby="ect-analysis" className="rounded-md border p-4">
      <h2 id="ect-analysis" className="text-lg font-semibold">Latest release analysis</h2>
      <div className="mt-3"><InsightList insights={a.executive_summary} /></div>
      <div className="mt-3"><InsightList insights={a.context} /></div>
      <p className="mt-3 text-sm text-muted-foreground">{a.revisions.note} {a.revisions.available?`${a.revisions.n_revised} of ${a.revisions.n_common} overlapping retail months were revised.`:''}</p>
      <Link className="mt-3 inline-block text-sm underline underline-offset-2" to={`/releases/${rel.id}`}>Full release analysis</Link>
    </section>
    <section aria-labelledby="ect-method" className="space-y-2">
      <h2 id="ect-method" className="text-lg font-semibold">Source and methodology</h2>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">{[...a.methodology.definitions,...a.methodology.notes].map(t=><li key={t}>{t}</li>)}</ul>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm underline underline-offset-2">
        {rel.page_url && <a href={rel.page_url} target="_blank" rel="noreferrer">Official Stats NZ release</a>}
        {selected?.source_url && <a href={selected.source_url} target="_blank" rel="noreferrer">Official historical CSV ZIP</a>}
        <a href="https://datainfoplus.stats.govt.nz/item/nz.govt.stats/3d0dfc89-6bf5-4677-8cef-3befc36f5b90" target="_blank" rel="noreferrer">DataInfo+ methodology</a>
      </div>
      <p className="text-xs text-muted-foreground">Data captured {formatAklDateTime(a.vintage_captured_at)}. {isStaticMode() ? "This site is updated after each verified Stats NZ release." : "Automatic refresh follows the official release calendar."} <Link className="underline" to="/health">Data health</Link></p>
    </section>
  </div>;
}

export default function ElectronicCardTransactions() {
  useDocumentTitle(ROUTE_META["/electronic-card-transactions"].title);
  const q=useEct();
  if(q.error instanceof ApiError && q.error.status===404) return isStaticMode()
    ? <EmptyState title="Card transactions data has not been published yet" body="This dashboard appears once a Stats NZ electronic card transactions release has been verified and published here." />
    : <EmptyState title="ECT data has not been ingested yet" body="The next scheduled refresh or an ECT backfill will populate this dashboard. Check Data health for ingestion status." />;
  return <QueryBoundary query={q}>{d=><Dashboard data={d} />}</QueryBoundary>;
}
