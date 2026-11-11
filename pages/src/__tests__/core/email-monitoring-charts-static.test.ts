// mail/js/email-monitoring.js: the Email Monitoring dashboard's SVG charts (columns, stacked columns, lines), their
// hover / keyboard tooltip, and the custom-range date fields. Series names are data: they must render as text.
import {afterEach, describe, expect, it} from 'vitest';

import {readRepoFile} from '@/__tests__/core/adminStatic';

const SCRIPT = 'src/apps/mail/static/mail/js/email-monitoring.js';

interface Series {
  names: {key: string; label: string}[];
  labels: string[];
  display: string[];
  series: Record<string, number[]>;
}

const series = (names: [string, string][], values: Record<string, number[]>): Series => {
  const count = Object.values(values)[0].length;
  return {
    names: names.map(([key, label]) => ({key, label})),
    labels: Array.from({length: count}, (_value, index) => `2026-11-0${index + 1}T00:00:00-08:00`),
    display: Array.from({length: count}, (_value, index) => `Nov 0${index + 1}`),
    series: values,
  };
};

function mount(payload: Record<string, Series>, charts: [string, string][]) {
  const json = document.createElement('script');
  json.type = 'application/json';
  json.id = 'i2g-monitor-charts';
  json.textContent = JSON.stringify(payload);
  document.body.appendChild(json);
  for (const [key, kind] of charts) {
    const figure = document.createElement('figure');
    figure.className = 'i2g-monitor-chart';
    figure.dataset.chart = key;
    figure.dataset.kind = kind;
    figure.dataset.source = 'i2g-monitor-charts';
    figure.innerHTML = `<h3>${key} chart</h3><div data-chart-plot></div>`;
    document.body.appendChild(figure);
  }
  window.eval(readRepoFile(SCRIPT));
}

const plot = (key: string) => document.querySelector(`[data-chart="${key}"] [data-chart-plot]`) as HTMLElement;
const tooltip = (key: string) => plot(key).querySelector('.i2g-monitor-tooltip') as HTMLElement;

afterEach(() => {
  document.body.replaceChildren();
});

describe('email monitoring charts', () => {
  it('draws one hit band per period and a column for each non-empty one', () => {
    mount({volume: series([['emails', 'Emails']], {emails: [3, 0, 12]})}, [['volume', 'columns']]);

    const svg = plot('volume').querySelector('svg') as SVGSVGElement;
    expect(svg.getAttribute('aria-label')).toContain('3 periods');
    expect(svg.querySelectorAll('.i2g-hit')).toHaveLength(3);
    expect(svg.querySelectorAll('path.i2g-fill-1')).toHaveLength(2);
    expect([...svg.querySelectorAll('.i2g-tick')].map((tick) => tick.textContent)).toContain('Nov 01');
  });

  it('shows every series of a band in its tooltip on focus, and moves with the arrow keys', () => {
    mount(
      {bounces: series([['hard', 'Hard bounce'], ['soft', 'Soft bounce']], {hard: [1, 4], soft: [2, 0]})},
      [['bounces', 'stacked']],
    );
    const hits = plot('bounces').querySelectorAll<SVGRectElement>('.i2g-hit');
    expect([...hits].map((hit) => hit.getAttribute('tabindex'))).toEqual(['-1', '0']);

    hits[1].dispatchEvent(new FocusEvent('focus'));
    expect(tooltip('bounces').hidden).toBe(false);
    expect(tooltip('bounces').textContent).toBe('Nov 024Hard bounce0Soft bounce');

    hits[1].dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft'}));
    expect(hits[0].getAttribute('tabindex')).toBe('0');
    expect(plot('bounces').querySelectorAll('rect.i2g-fill-1')).toHaveLength(1);
  });

  it('draws lines with a focusable crosshair that reads each period', () => {
    mount(
      {api: series([['accepted', 'Accepted'], ['failed', 'Failed']], {accepted: [5, 7, 9], failed: [1, 0, 2]})},
      [['api', 'lines']],
    );
    const overlay = plot('api').querySelector('.i2g-hit') as SVGRectElement;

    overlay.dispatchEvent(new FocusEvent('focus'));
    expect(tooltip('api').textContent).toBe('Nov 039Accepted2Failed');
    overlay.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft'}));
    expect(tooltip('api').textContent).toBe('Nov 027Accepted0Failed');
    expect(plot('api').querySelectorAll('path.i2g-line')).toHaveLength(2);
    expect(plot('api').querySelector('.i2g-crosshair')?.getAttribute('visibility')).toBe('visible');
  });

  it('renders series names as text, never as markup', () => {
    const name = '<img src=x onerror="window.pwned=1">';
    mount({volume: series([['emails', name]], {emails: [1]})}, [['volume', 'columns']]);

    plot('volume').querySelector('.i2g-hit')?.dispatchEvent(new FocusEvent('focus'));

    expect(tooltip('volume').querySelector('img')).toBeNull();
    expect(tooltip('volume').textContent).toContain(name);
  });

  it('draws nothing for a chart without periods or without its data', () => {
    mount({volume: series([['emails', 'Emails']], {emails: []})}, [['volume', 'columns'], ['missing', 'lines']]);

    expect(plot('volume').querySelector('svg')).toBeNull();
    expect(plot('missing').querySelector('svg')).toBeNull();
  });

  it('shows the custom range dates only for a custom range', () => {
    document.body.innerHTML = `
      <select data-monitor-range><option value="7d">7 days</option><option value="custom">Custom</option></select>
      <label data-monitor-custom><input name="start"></label>`;
    window.eval(readRepoFile(SCRIPT));
    const select = document.querySelector('select') as HTMLSelectElement;
    const field = document.querySelector('[data-monitor-custom]') as HTMLElement;

    expect(field.hidden).toBe(true);
    expect((field.querySelector('input') as HTMLInputElement).disabled).toBe(true);
    select.value = 'custom';
    select.dispatchEvent(new Event('change'));
    expect(field.hidden).toBe(false);
  });
});
