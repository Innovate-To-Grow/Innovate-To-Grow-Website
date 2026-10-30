/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {afterEach, describe, expect, it, vi} from 'vitest';

import {exportProjectRowsPdf} from '@/features/projects/components/export/formats/pdfExport';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// The real jsPDF, recording each line it draws (with the font it is drawn in) and the bytes `save` would download.
const recorded = vi.hoisted(() => ({
  drawn: [] as Array<{family: string; text: string}>,
  saved: [] as Uint8Array[],
}));

vi.mock('jspdf', async (importOriginal) => {
  const actual = await importOriginal<typeof import('jspdf')>();
  function RecordingJsPdf(options: ConstructorParameters<typeof actual.jsPDF>[0]) {
    const pdf = new actual.jsPDF(options);
    const draw = pdf.text.bind(pdf) as (...args: unknown[]) => unknown;
    pdf.text = ((value: string | string[], ...rest: unknown[]) => {
      for (const text of Array.isArray(value) ? value : [value]) {
        recorded.drawn.push({family: pdf.getFont().fontName, text});
      }
      return draw(value, ...rest);
    }) as unknown as typeof pdf.text;
    pdf.save = (() => {
      recorded.saved.push(new Uint8Array(pdf.output('arraybuffer')));
      return pdf;
    }) as unknown as typeof pdf.save;
    return pdf;
  }
  return {...actual, jsPDF: RecordingJsPdf};
});

const publicDir = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../../public');

/** Serve /assets/** from pages/public, as the site does; URLs matching `missing` answer 404. */
const servePublicAssets = (missing?: RegExp) => {
  const fetchMock = vi.fn(async (url: string) => {
    if (missing?.test(url)) {
      return {ok: false, arrayBuffer: async () => new ArrayBuffer(0)};
    }
    const file = readFileSync(resolve(publicDir, `.${url}`));
    return {ok: true, arrayBuffer: async () => file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength)};
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

const row = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
  semester_label: '2025 Spring',
  class_code: 'CSE',
  team_number: '7',
  team_name: 'Rotary Team',
  project_title: 'Rotary Joint Testing System',
  organization: 'E&J Gallo Winery',
  industry: 'Food Processing',
  abstract: 'A short abstract.',
  student_names: 'Alice Calderon, Bob Lee',
  is_presenting: '',
  ...overrides,
});

// Names and text as they appear in the archive: a non-breaking hyphen, accents outside Windows-1252, Greek, a
// combining mark and emoji.
const unicodeRow = row({
  project_title: 'Farm\u2011NG Amiga Robot',
  team_name: '\u{1f96d}MangoDB\u{1f96d}',
  organization: 'T\u035fH\u0113 L\u014dk\u0101t\u0259rs',
  industry: '\u03c9SST',
  student_names: 'Ana \u017divanovi\u0107, Nguy\u1ec5n V\u0103n An, \u0141ukasz',
  abstract: 'A real\u2011time pipeline.',
});

const drawnTexts = () => recorded.drawn.map((entry) => entry.text);
const savedPdfText = () => new TextDecoder('latin1').decode(recorded.saved[0]);

afterEach(() => {
  vi.unstubAllGlobals();
  recorded.drawn.length = 0;
  recorded.saved.length = 0;
});

describe('exportProjectRowsPdf with the real jsPDF', () => {
  it('keeps the PDF small: one compressed, print-sized logo shared by every page', async () => {
    servePublicAssets();

    await exportProjectRowsPdf([row()], 'past-projects');
    const onePage = recorded.saved[0];
    await exportProjectRowsPdf(Array.from({length: 40}, (_, index) => row({team_number: String(index + 1)})), 'many');
    const manyPages = recorded.saved[1];

    // The full-size logo embedded as raw pixels made every PDF about 16.6 MB.
    expect(onePage.byteLength).toBeLessThan(150_000);
    expect(manyPages.byteLength).toBeLessThan(250_000);
    const manyText = new TextDecoder('latin1').decode(manyPages);
    // The logo and its alpha mask, written once for all the pages.
    expect(manyText.match(/\/Subtype \/Image/g)).toHaveLength(2);
    expect(manyText).toContain('/FlateDecode');
  });

  it('draws names, accents and hyphens outside Windows-1252 in the embedded Open Sans', async () => {
    servePublicAssets();

    await exportProjectRowsPdf([unicodeRow], 'past-projects', {title: 'Curation \u2011 2025'});

    expect(new Set(recorded.drawn.map((entry) => entry.family))).toEqual(new Set(['OpenSans']));
    expect(drawnTexts()).toEqual(
      expect.arrayContaining([
        'Curation - 2025',
        'Project 1: Farm-NG Amiga Robot',
        'MangoDB',
        'TH\u0113 L\u014dk\u0101t\u0259rs',
        '\u03c9SST',
        'Ana \u017divanovi\u0107, Nguy\u1ec5n V\u0103n An, \u0141ukasz',
        'A real-time pipeline.',
      ]),
    );
    expect(savedPdfText()).toMatch(/\/FontFile2/);
    expect(savedPdfText()).toMatch(/\/BaseFont \/OpenSans/);
  });

  it('falls back to Helvetica with Windows-1252 text when the fonts cannot be loaded', async () => {
    servePublicAssets(/\/fonts\//);

    await exportProjectRowsPdf([unicodeRow], 'past-projects');

    expect(new Set(recorded.drawn.map((entry) => entry.family))).toEqual(new Set(['helvetica']));
    expect(drawnTexts()).toEqual(
      expect.arrayContaining([
        'Project 1: Farm-NG Amiga Robot',
        'MangoDB',
        'THe Lokatrs',
        'SST',
        'Ana \u017divanovic, Nguyen Van An, Lukasz',
        'A real-time pipeline.',
      ]),
    );
    expect(recorded.saved).toHaveLength(1);
  });

  it('loads the italic faces only for a note that uses them', async () => {
    const fetchMock = servePublicAssets();
    const fontsFetched = () =>
      fetchMock.mock.calls.map(([url]) => url).filter((url) => url.includes('/fonts/')).sort();

    await exportProjectRowsPdf([row()], 'plain');
    expect(fontsFetched()).toEqual([
      '/assets/fonts/open-sans/OpenSans-Bold.ttf',
      '/assets/fonts/open-sans/OpenSans-Regular.ttf',
    ]);

    fetchMock.mockClear();
    await exportProjectRowsPdf([row()], 'noted', {note: '<p>Read <em>this</em> first</p>'});
    expect(fontsFetched()).toEqual([
      '/assets/fonts/open-sans/OpenSans-Bold.ttf',
      '/assets/fonts/open-sans/OpenSans-Italic.ttf',
      '/assets/fonts/open-sans/OpenSans-Regular.ttf',
    ]);
    expect(recorded.drawn).toEqual(expect.arrayContaining([{family: 'OpenSans', text: 'this'}]));
  });
});
