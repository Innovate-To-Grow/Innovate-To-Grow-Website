/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {jsPDF} from 'jspdf';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {loadPdfFontFiles, registerPdfTypeface} from '@/features/projects/components/export/support/pdfTypeface';

const fontDir = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../../public/assets/fonts/open-sans');
const fontBase64 = (file: string) => readFileSync(resolve(fontDir, file)).toString('base64');
const answer = (bytes: Uint8Array) => ({ok: true, arrayBuffer: async () => bytes.buffer});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('loadPdfFontFiles', () => {
  it('fetches each requested face once', async () => {
    const font = Uint8Array.from([0, 1, 0, 0, 0, 12]);
    const fetchMock = vi.fn<(url: string) => Promise<ReturnType<typeof answer>>>(async () => answer(font));
    vi.stubGlobal('fetch', fetchMock);

    const files = await loadPdfFontFiles(['normal', 'bold', 'normal']);

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/assets/fonts/open-sans/OpenSans-Regular.ttf',
      '/assets/fonts/open-sans/OpenSans-Bold.ttf',
    ]);
    expect(files?.map((file) => file.style)).toEqual(['normal', 'bold']);
  });

  it('gives up when a face is missing or the answer is not a font', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ok: false})));
    expect(await loadPdfFontFiles(['normal'])).toBeNull();

    // An SPA rewrite or error page answers 200 with HTML.
    vi.stubGlobal('fetch', vi.fn(async () => answer(new TextEncoder().encode('<!doctype html><html></html>'))));
    expect(await loadPdfFontFiles(['normal'])).toBeNull();
  });
});

describe('registerPdfTypeface', () => {
  it('embeds Open Sans and keeps only what its glyphs can draw', () => {
    const pdf = new jsPDF();
    const typeface = registerPdfTypeface(pdf, [
      {style: 'normal', base64: fontBase64('OpenSans-Regular.ttf')},
      {style: 'bold', base64: fontBase64('OpenSans-Bold.ttf')},
    ]);

    expect(typeface.family).toBe('OpenSans');
    expect(pdf.getFontList().OpenSans).toEqual(['normal', 'bold']);
    expect(typeface.drawable('Ana \u017divanovi\u0107 \u03c9SST real\u2011time \u{1f96d}')).toBe(
      'Ana \u017divanovi\u0107 \u03c9SST real-time ',
    );
  });

  it('uses Helvetica and Windows-1252 text without fonts', () => {
    const typeface = registerPdfTypeface(new jsPDF(), null);

    expect(typeface.family).toBe('helvetica');
    expect(typeface.drawable('Ana \u017divanovi\u0107 \u03c9SST')).toBe('Ana \u017divanovic SST');
  });

  it('uses Helvetica when jsPDF cannot read a face', () => {
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const corrupt = btoa(String.fromCharCode(0, 1, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0));

    const pdf = new jsPDF();
    const typeface = registerPdfTypeface(pdf, [{style: 'normal', base64: corrupt}]);

    expect(typeface.family).toBe('helvetica');
    expect(logged).toHaveBeenCalled();
    // The document still writes out with the text in Helvetica.
    pdf.setFont(typeface.family, 'normal');
    pdf.text(typeface.drawable('Team'), 10, 10);
    expect(pdf.output('arraybuffer').byteLength).toBeGreaterThan(0);
  });
});
