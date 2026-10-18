import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import data from '@/test/fixtures/ect.json';
import { mockApi, renderWithProviders } from '@/test/mockApi';
import ElectronicCardTransactions from './ElectronicCardTransactions';

vi.mock('@/charts/EChart', () => ({ EChart: ({ariaLabel,option}: {ariaLabel:string;option:unknown}) =>
  <div role="img" aria-label={ariaLabel} data-option={JSON.stringify(option)} /> }));
beforeEach(() => mockApi({'/api/ect':data}));

it('shows verified KPIs, actual distinctions, findings, sources and CSV exports', async () => {
  renderWithProviders(<ElectronicCardTransactions />);
  expect(await screen.findByRole('heading',{name:'Electronic card transactions',level:1})).toBeInTheDocument();
  expect(screen.getByRole('region',{name:'ECT key indicators'})).toHaveTextContent('−0.4%');
  expect(screen.getByRole('region',{name:'ECT key indicators'})).toHaveTextContent('−0.7%');
  expect(screen.getByRole('heading',{name:'Latest release analysis'})).toBeInTheDocument();
  expect(screen.getByText(/not all retail sales or all household consumption/)).toBeInTheDocument();
  expect(screen.getAllByRole('button',{name:/download data/i})).toHaveLength(3);
  expect(screen.getByRole('link',{name:'Full release analysis'})).toHaveAttribute('href',`/releases/${data.analysis.release.id}`);
});

it('switches aggregate, adjustment, history window and official quarterly frequency', async () => {
  renderWithProviders(<ElectronicCardTransactions />);
  const user=userEvent.setup();
  const history=await screen.findByRole('img',{name:'ECT spending history'});
  const initial=history.getAttribute('data-option');
  await user.selectOptions(screen.getByLabelText('Spending group'),'core');
  expect(history.getAttribute('data-option')).not.toBe(initial);
  await user.selectOptions(screen.getByLabelText('Adjustment'),'actual');
  expect(history.getAttribute('data-option')).toContain('Actual');
  await user.click(within(screen.getByRole('group',{name:'History window'})).getByRole('radio',{name:'1 year'}));
  const option=JSON.parse(history.getAttribute('data-option')!);
  expect(option.xAxis.data).toHaveLength(12);
  await user.click(within(screen.getByRole('group',{name:'ECT frequency'})).getByRole('radio',{name:'Quarterly'}));
  const quarterly=JSON.parse(history.getAttribute('data-option')!);
  expect(quarterly.xAxis.data).toHaveLength(4);
  expect(quarterly.xAxis.data.every((p:string)=>/-(03|06|09|12)$/.test(p))).toBe(true);
});

it('shows accurate negative industry movements and uses actual composition', async () => {
  renderWithProviders(<ElectronicCardTransactions />);
  const movements=await screen.findByRole('img',{name:'ECT industry movements'});
  const opt=JSON.parse(movements.getAttribute('data-option')!);
  expect(opt.series[0].data.some((p:{value:number})=>p.value<0)).toBe(true);
  expect(opt.xAxis.min).toBeLessThan(0);
  expect(screen.getByRole('heading',{name:/Spending composition.*actual/i})).toBeInTheDocument();
});

it('only offers quarterly when the selected series exists in this bundle', async () => {
  mockApi({'/api/ect':{...data,series:data.series.filter(s=>s.series.frequency!=='quarterly')}});
  renderWithProviders(<ElectronicCardTransactions />);
  await screen.findByRole('heading',{name:'Electronic card transactions',level:1});
  expect(screen.queryByRole('radio',{name:'Quarterly'})).not.toBeInTheDocument();
  expect(screen.getByText(/Quarterly data is not available/)).toBeInTheDocument();
});

it('explains an unseeded database', async () => {
  mockApi({});renderWithProviders(<ElectronicCardTransactions />);
  expect(await screen.findByText(/ECT data has not been ingested/)).toBeInTheDocument();
});

it('zooms the level chart by default with an explicit non-zero axis note, and can return to a zero base', async () => {
  renderWithProviders(<ElectronicCardTransactions />);
  const user=userEvent.setup();
  const history=await screen.findByRole('img',{name:'ECT spending history'});
  const scale=screen.getByRole('group',{name:'Vertical scale'});
  expect(within(scale).getByRole('radio',{name:'Zoomed'})).toBeChecked();
  const zoomed=JSON.parse(history.getAttribute('data-option')!);
  expect(zoomed.yAxis.min).toBeGreaterThan(0);
  expect(zoomed.title.text).toMatch(/not zero/);
  expect(screen.getByText(/Vertical axis starts at \$[\d.]+b, not zero/)).toBeInTheDocument();
  await user.click(within(scale).getByRole('radio',{name:'From zero'}));
  const zero=JSON.parse(history.getAttribute('data-option')!);
  expect(zero.yAxis.min).toBe(0);
  expect(screen.queryByText(/Vertical axis starts at/)).not.toBeInTheDocument();
});

it('words the latest-release analysis as plain sentences', async () => {
  renderWithProviders(<ElectronicCardTransactions />);
  await screen.findByRole('heading',{name:'Latest release analysis'});
  expect(screen.queryByText(/, value[:,]/)).not.toBeInTheDocument();
});
