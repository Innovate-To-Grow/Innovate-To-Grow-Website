// mail/js/email-monitoring-ses.js: Email Monitoring → Amazon SES (the former Delivery Dashboard). It filters the
// server-rendered suppression-list rows (search and status), keeps the "Showing" count, and exports the rows shown as
// CSV, TSV, JSON or an Excel sheet, never as a live spreadsheet formula. Values are data: they must stay text.
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {readRepoFile} from '@/__tests__/core/adminStatic';

const SCRIPT = 'src/apps/mail/static/mail/js/email-monitoring-ses.js';

interface Row {
  email: string;
  domain: string;
  status: string;
  label: string;
  lastSeen: string;
  reason: string;
  source: string;
  context: string;
}

const ROWS: Row[] = [
  {
    email: 'bounce@example.com', domain: 'example.com', status: 'bounced', label: 'Bounced',
    lastSeen: 'Jun 08, 12:00', reason: 'BOUNCE', source: 'AWS SES Suppression List', context: 'Account-level suppression',
  },
  {
    email: 'complaint@example.org', domain: 'example.org', status: 'complained', label: 'Complained',
    lastSeen: 'Jun 07, 12:00', reason: 'COMPLAINT', source: 'AWS SES Suppression List', context: 'Account-level suppression',
  },
  {
    email: '=cmd@example.net', domain: 'example.net', status: 'bounced', label: 'Bounced',
    lastSeen: 'Jun 01, 09:30', reason: 'BOUNCE', source: 'AWS SES, "list"', context: '<b>x</b>',
  },
];

function mount(rows: Row[] = ROWS) {
  const section = document.createElement('section');
  section.dataset.sesRecipients = '';
  section.dataset.windowDays = '183';
  section.dataset.windowLabel = 'Last 6 months';
  section.dataset.windowShort = '6mo';
  section.innerHTML = `
    <strong data-ses-showing>${rows.length}</strong>
    <input type="search" data-ses-search>
    <select data-ses-status><option value="all">All</option><option value="bounced">Bounced</option><option value="complained">Complained</option></select>
    <select data-ses-format><option value="csv">CSV</option><option value="tsv">TSV</option><option value="json">JSON</option><option value="xls">Excel</option></select>
    <button type="button" data-ses-export>Export</button>
    <table><tbody></tbody></table>
    <p data-ses-no-match hidden>No recipients match the current filters.</p>`;
  const body = section.querySelector('tbody') as HTMLTableSectionElement;
  for (const row of rows) {
    const tr = document.createElement('tr');
    tr.setAttribute('data-ses-row', '');
    Object.assign(tr.dataset, row);
    tr.textContent = row.email;
    body.appendChild(tr);
  }
  document.body.appendChild(section);
  window.eval(readRepoFile(SCRIPT));
  return section;
}

const $ = <T extends Element>(selector: string) => document.querySelector(selector) as T;
const shown = () => [...document.querySelectorAll<HTMLTableRowElement>('[data-ses-row]')].filter((row) => !row.hidden);

function search(text: string) {
  const input = $<HTMLInputElement>('[data-ses-search]');
  input.value = text;
  input.dispatchEvent(new Event('input'));
}

function choose(selector: string, value: string) {
  const select = $<HTMLSelectElement>(selector);
  select.value = value;
  select.dispatchEvent(new Event('change'));
}

let blobs: Blob[] = [];
let downloads: string[] = [];

beforeEach(() => {
  blobs = [];
  downloads = [];
  vi.useFakeTimers({toFake: ['Date']});
  vi.setSystemTime(new Date('2026-11-12T10:00:00Z'));
  Object.assign(URL, {
    createObjectURL: vi.fn((blob: Blob) => {
      blobs.push(blob);
      return `blob:export-${blobs.length}`;
    }),
    revokeObjectURL: vi.fn(),
  });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    downloads.push(this.download);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.body.replaceChildren();
});

async function exported(format: string) {
  choose('[data-ses-format]', format);
  $<HTMLButtonElement>('[data-ses-export]').click();
  expect(blobs).toHaveLength(1);
  return {name: downloads[0], type: blobs[0].type, text: await blobs[0].text()};
}

describe('email monitoring: Amazon SES suppression list', () => {
  it('searches the address, domain, reason, status and source, ignoring case', () => {
    mount();

    search('EXAMPLE.ORG');
    expect(shown().map((row) => row.dataset.email)).toEqual(['complaint@example.org']);
    expect($('[data-ses-showing]').textContent).toBe('1 / 3');

    search('bounce');
    expect(shown()).toHaveLength(2);

    search('account-level');
    expect(shown()).toHaveLength(2);

    search('aws ses');
    expect(shown()).toHaveLength(3);
    expect($('[data-ses-showing]').textContent).toBe('3');
  });

  it('filters by status together with the search', () => {
    mount();

    choose('[data-ses-status]', 'bounced');
    expect(shown().map((row) => row.dataset.email)).toEqual(['bounce@example.com', '=cmd@example.net']);

    search('example.net');
    expect(shown().map((row) => row.dataset.email)).toEqual(['=cmd@example.net']);
  });

  it('says when nothing matches and offers no empty export', () => {
    mount();

    search('nobody-at-all');

    expect(shown()).toHaveLength(0);
    expect($<HTMLElement>('[data-ses-no-match]').hidden).toBe(false);
    expect($<HTMLButtonElement>('[data-ses-export]').disabled).toBe(true);
    $<HTMLButtonElement>('[data-ses-export]').click();
    expect(blobs).toHaveLength(0);

    search('');
    expect($<HTMLElement>('[data-ses-no-match]').hidden).toBe(true);
    expect($<HTMLButtonElement>('[data-ses-export]').disabled).toBe(false);
  });

  it('exports the rows shown as CSV, quoted, and never as a live formula', async () => {
    mount();
    choose('[data-ses-status]', 'bounced');

    const file = await exported('csv');

    expect(file.name).toBe('ses-problem-recipients-6mo-2026-11-12.csv');
    expect(file.type).toBe('text/csv;charset=utf-8');
    expect(file.text.split('\n')).toEqual([
      'Email,Domain,Status,Last Seen,Reason,Source,Context',
      'bounce@example.com,example.com,Bounced,"Jun 08, 12:00",BOUNCE,AWS SES Suppression List,Account-level suppression',
      `'=cmd@example.net,example.net,Bounced,"Jun 01, 09:30",BOUNCE,"AWS SES, ""list""",<b>x</b>`,
      '',
    ]);
  });

  it('exports TSV with the same columns', async () => {
    mount();
    search('complaint');

    const file = await exported('tsv');

    expect(file.name).toBe('ses-problem-recipients-6mo-2026-11-12.tsv');
    expect(file.text).toBe(
      'Email\tDomain\tStatus\tLast Seen\tReason\tSource\tContext\n' +
        'complaint@example.org\texample.org\tComplained\tJun 07, 12:00\tCOMPLAINT\tAWS SES Suppression List\t' +
        'Account-level suppression\n',
    );
  });

  it('exports JSON with the range, the filters and the records as they are', async () => {
    mount();
    search('example.net');

    const file = await exported('json');
    const payload = JSON.parse(file.text);

    expect(file.name).toBe('ses-problem-recipients-6mo-2026-11-12.json');
    expect(payload).toMatchObject({
      generated_at: '2026-11-12T10:00:00.000Z',
      window_days: 183,
      window_label: 'Last 6 months',
      filters: {query: 'example.net', status: 'all'},
      count: 1,
    });
    expect(payload.records[0].Email).toBe('=cmd@example.net');
    expect(payload.records[0].Context).toBe('<b>x</b>');
  });

  it('exports an Excel sheet whose cells are escaped text', async () => {
    mount();

    const file = await exported('xls');

    expect(file.name).toBe('ses-problem-recipients-6mo-2026-11-12.xls');
    expect(file.type).toBe('application/vnd.ms-excel;charset=utf-8');
    expect(file.text).toContain('<th>Last Seen</th>');
    expect(file.text).toContain('<td>&#39;=cmd@example.net</td>');
    expect(file.text).toContain('<td>&lt;b&gt;x&lt;/b&gt;</td>');
    expect(file.text).not.toContain('<b>x</b>');
    expect(file.text.match(/<tr>/g)).toHaveLength(4);
  });

  it('does nothing on a page without rows', () => {
    mount([]);

    search('anything');

    expect($('[data-ses-showing]').textContent).toBe('0');
    expect($<HTMLElement>('[data-ses-no-match]').hidden).toBe(true);
  });
});
