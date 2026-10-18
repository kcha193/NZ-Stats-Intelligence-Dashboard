import { expect, it } from 'vitest';
import { ectHistoryOption, ectIndustryOption, zoomedRange } from './ect';
import { TEST_THEME } from './theme';

it('formats money with NZD units, adjustment and quarterly periods in tooltips', () => {
  const opt=ectHistoryOption({name:'Retail, Seasonally adjusted',points:[{period:'2026-09',value:21085.9,status:'unknown'}],frequency:'quarterly'},TEST_THEME) as any;
  expect(opt.xAxis.data).toEqual(['2026-09']);
  expect(opt.xAxis.axisLabel.interval).toBe(0);
  const tip=opt.tooltip.formatter([{axisValue:'2026-09',seriesName:'Retail, Seasonally adjusted',value:21085.9,marker:''}]);
  expect(tip).toContain('Quarter ended');expect(tip).toContain('21,085.9');expect(tip).toContain('NZD million');
  expect(tip).toContain('Seasonally adjusted');
  expect(opt.yAxis.axisLabel.formatter(21000)).toContain('21');
});

it('has a zero reference, signed bars and escaped industry text', () => {
  const opt=ectIndustryOption([{name:'<Hospitality>',value:-2.3},{name:'Fuel',value:2.9}],TEST_THEME,'percent') as any;
  expect(opt.xAxis.min).toBeLessThan(0);
  expect(opt.series[0].markLine.data).toEqual([{xAxis:0}]);
  expect(opt.tooltip.formatter({name:'<Hospitality>',value:-2.3,data:{provisional:false}})).toContain('&lt;Hospitality&gt;');
});

const levels = [6800, 6900, 7000, 6950, 6976].map((value, i) => ({ period: `2026-0${i + 1}`, value, status: 'final' }));

it('derives a padded, never-negative zoomed range that contains every value', () => {
  const r = zoomedRange(levels);
  expect(r.min).toBeGreaterThan(0);
  expect(r.min).toBeLessThan(6800);
  expect(r.max).toBeGreaterThan(7000);
  expect(zoomedRange([{ period: '2026-01', value: 100, status: 'final' }, { period: '2026-02', value: 100, status: 'final' }]).min).toBeLessThan(100);
  expect(zoomedRange([{ period: '2026-01', value: 5, status: 'final' }, { period: '2026-02', value: 900, status: 'final' }]).min).toBeGreaterThanOrEqual(0);
});

it('zoomed level charts label the truncated axis inside the chart; from-zero charts do not', () => {
  const zoomed = ectHistoryOption({ name: 'Retail, Seasonally adjusted', points: levels, frequency: 'monthly' }, TEST_THEME, 'zoomed') as any;
  const { min } = zoomedRange(levels);
  expect(zoomed.yAxis.min).toBe(min);
  expect(zoomed.title.text).toContain('not zero');
  expect(zoomed.title.text).toContain(`$${(min / 1000).toFixed(2)}b`);
  expect(zoomed.yAxis.axisLabel.formatter(6900)).toBe('$6.90b');
  const zero = ectHistoryOption({ name: 'Retail, Seasonally adjusted', points: levels, frequency: 'monthly' }, TEST_THEME, 'zero') as any;
  expect(zero.yAxis.min).toBe(0);
  expect(zero.title).toBeUndefined();
});

it('zoomed tooltips still show exact values in NZD million', () => {
  const opt = ectHistoryOption({ name: 'Retail, Seasonally adjusted', points: levels, frequency: 'monthly' }, TEST_THEME, 'zoomed') as any;
  const tip = opt.tooltip.formatter([{ axisValue: '2026-05', value: 6976 }]);
  expect(tip).toContain('6,976.0'); expect(tip).toContain('NZD million');
});

it('industry charts size to their labels and use whole-number negative ticks on narrow screens', () => {
  const opt = ectIndustryOption([{ name: 'Motor vehicles excl. fuel', value: 0.6 }, { name: 'Hospitality', value: -2.26 }], TEST_THEME, 'percent') as any;
  expect(opt.grid.containLabel).toBe(true);
  expect(opt.yAxis.axisLabel.width).toBeLessThanOrEqual(120);
  expect(opt.yAxis.axisLabel.overflow).toBe('break');
  expect(Number.isInteger(opt.xAxis.min)).toBe(true);
  expect(opt.xAxis.min).toBeLessThanOrEqual(-2.26);
  expect(opt.xAxis.splitNumber).toBeLessThanOrEqual(4);
  expect(opt.xAxis.axisLabel.hideOverlap).toBe(true);
});
