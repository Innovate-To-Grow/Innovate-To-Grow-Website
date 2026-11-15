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
});
