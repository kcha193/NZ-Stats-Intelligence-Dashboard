import { expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import data from '@/test/fixtures/ect.json';
import overview from '@/test/fixtures/overview.json';
import { mockApi, renderWithProviders } from '@/test/mockApi';
import ReleaseAnalysis from './ReleaseAnalysis';
import Overview from './Overview';

vi.mock('@/charts/EChart',()=>({EChart:()=>null}));

it('renders ECT release analysis using money and transaction units',async()=>{
  const rel=data.analysis.release;
  mockApi({[`/api/releases/${rel.id}`]:{release:rel,analysis:data.analysis,unavailable_reason:null}});
  renderWithProviders(<Routes><Route path="/releases/:id" element={<ReleaseAnalysis />} /></Routes>,{route:`/releases/${rel.id}`});
  const table=await screen.findByRole('table',{name:'Headline metrics'});
  expect(table).toHaveTextContent('NZD million');expect(table).toHaveTextContent('transactions');
  expect(table).not.toHaveTextContent('people');
  const rev=screen.getByRole('heading',{name:'Revision analysis'}).closest('section')!;
  expect(rev).toHaveTextContent('110');expect(rev).toHaveTextContent('NZD million');
});

it('keeps an ECT indicator visible alongside all migration KPIs and links its dashboard',async()=>{
  const metric=data.analysis.headline_metrics[0];
  mockApi({'/api/overview':{...overview,kpis:[...overview.kpis,{metric,release_id:data.analysis.release.id,published_at:data.analysis.release.published_at,source_url:data.analysis.release.page_url}]}});
  renderWithProviders(<Overview />);
  const indicators=await screen.findByRole('region',{name:'Key indicators'});
  expect(within(indicators).getByRole('article',{name:metric.label})).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Explore card spending'})).toHaveAttribute('href','/electronic-card-transactions');
});
