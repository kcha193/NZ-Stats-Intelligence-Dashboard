import { expect, it } from 'vitest';
import { ectHistoryOption, ectIndustryOption } from './ect';
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
