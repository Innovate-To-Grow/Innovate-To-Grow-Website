import ExcelJS from 'exceljs';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {buildProjectsWorksheet} from './excelExport';
import {exportProjectRowsPdf} from './pdfExport';
import {createProjectRowsWordBlob} from './wordExport';
import {loadI2gLogoAsset} from './logoAsset';
import {parseRichTextRuns, runsToPlainText} from './exportRichText';
import type {ProjectGridRow} from '../projectGrid';

// jspdf is heavy and DOM/canvas-bound; mock it so we can assert the document assembly wiring
// (sections + per-project field lines drawn) without rendering a real PDF.
const pdfTextCalls = vi.hoisted(() => [] as string[]);

vi.mock('jspdf', () => {
  class MockJsPdf {
    internal = {pageSize: {getWidth: () => 297, getHeight: () => 210}};
    setTextColor = vi.fn();
    setFont = vi.fn();
    setFontSize = vi.fn();
    setDrawColor = vi.fn();
    setFillColor = vi.fn();
    line = vi.fn();
    rect = vi.fn();
    addPage = vi.fn();
    addImage = vi.fn();
    save = vi.fn();
    getTextWidth(text: string) {
      return text.length;
    }
    splitTextToSize(text: string) {
      return [text];
    }
    text(value: string | string[]) {
      pdfTextCalls.push(...(Array.isArray(value) ? value : [value]));
    }
  }
  return {jsPDF: MockJsPdf};
});

const row: ProjectGridRow = {
  semester_label: '2025 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'General Rotary and Professional Engineering',
  project_title: 'Rotary Joint Testing System',
  organization: 'E&J Gallo Winery',
  industry: 'Food Processing',
  abstract: 'A detailed abstract with <special> characters & project context.',
  student_names: 'Alice Calderon, Bob Lee',
  is_presenting: '',
  curation: '<strong>Won first place</strong> with <mark>strong</mark> feedback & support',
};

const logo = {
  base64: 'iVBORw0KGgo=',
  bytes: Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]),
  dataUrl: 'data:image/png;base64,iVBORw0KGgo=',
  extension: 'png' as const,
};

describe('parseRichTextRuns', () => {
  it('splits a note into styled runs preserving bold / italic / underline / highlight', () => {
    const runs = parseRichTextRuns('<strong>Bold</strong> plain <mark>mark</mark> <em>it</em> <u>ul</u>');
    expect(runs.find((part) => part.text === 'Bold')?.bold).toBe(true);
    expect(runs.find((part) => part.text === 'mark')?.highlight).toBe(true);
    expect(runs.find((part) => part.text === 'it')?.italic).toBe(true);
    expect(runs.find((part) => part.text === 'ul')?.underline).toBe(true);
    expect(runsToPlainText(runs)).toContain('Bold plain mark it ul');
  });

  it('turns <br> and block boundaries into newlines', () => {
    const runs = parseRichTextRuns('line one<br>line two<div>line three</div>');
    expect(runsToPlainText(runs)).toBe('line one\nline two\nline three');
  });

  it('returns an empty array for blank notes', () => {
    expect(parseRichTextRuns('')).toEqual([]);
    expect(parseRichTextRuns('<div></div>')).toEqual([]);
  });

  it('drops disallowed markup but keeps the inner text', () => {
    const runs = parseRichTextRuns('<script>alert(1)</script>safe');
    expect(runsToPlainText(runs)).toContain('safe');
    expect(runsToPlainText(runs)).not.toContain('<script>');
  });
});

describe('createProjectRowsWordBlob', () => {
  it('creates a real docx package with per-project notes and branding', async () => {
    const blob = createProjectRowsWordBlob(
      [row],
      {title: 'Shared Results', note: 'Owner note & review instructions'},
      logo,
    );

    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document');

    const bytes = new Uint8Array(await blob.arrayBuffer());
    expect(String.fromCharCode(...bytes.slice(0, 2))).toBe('PK');

    const packageText = new TextDecoder().decode(bytes);
    expect(packageText).toContain('[Content_Types].xml');
    expect(packageText).toContain('word/document.xml');
    expect(packageText).toContain('word/media/i2g-logo.png');
    expect(packageText).toContain('Shared Results');
    expect(packageText).toContain('Owner note &amp; review instructions');
    // Per-project columns include the rich note (Notes column header + the note text).
    expect(packageText).toContain('Notes');
    expect(packageText).toContain('Won first place');
    expect(packageText).toContain('A detailed abstract with &lt;special&gt; characters &amp; project context.');
    // Bold + highlight markup is preserved as Word run properties.
    expect(packageText).toContain('<w:b/>');
    expect(packageText).toContain('w:fill="FFF3A3"');
  });

  it('omits the logo parts from the Word package when no logo is provided', async () => {
    const blob = createProjectRowsWordBlob([row], {title: 'No Logo Export'});
    const packageText = new TextDecoder().decode(new Uint8Array(await blob.arrayBuffer()));

    expect(packageText).not.toContain('rIdLogo');
    expect(packageText).not.toContain('word/media/i2g-logo.png');
    expect(packageText).toContain('No Logo Export');
    expect(packageText).toContain('Rotary Joint Testing System');
  });
});

describe('buildProjectsWorksheet', () => {
  it('builds a branded worksheet with the Notes column, project rows, and embedded logo', () => {
    const workbook = new ExcelJS.Workbook();
    buildProjectsWorksheet(workbook, [row], {title: 'Excel Title', note: 'Owner note'}, logo);

    const worksheet = workbook.getWorksheet('Projects');
    expect(worksheet).toBeDefined();
    expect(worksheet?.getCell(1, 2).value).toBe('Excel Title');
    expect(worksheet?.getCell(2, 2).value).toBe('Innovate to Grow Past Projects');
    expect(worksheet?.getImages()).toHaveLength(1);
    // 10 columns including Notes.
    expect(worksheet?.columns).toHaveLength(10);

    const cellText: string[] = [];
    worksheet?.eachRow((sheetRow) =>
      sheetRow.eachCell((cell) => {
        const value = cell.value as {richText?: Array<{text: string}>} | string | null;
        if (value && typeof value === 'object' && 'richText' in value && value.richText) {
          cellText.push(value.richText.map((part) => part.text).join(''));
        } else {
          cellText.push(String(value ?? ''));
        }
      }),
    );
    const joined = cellText.join('|');
    expect(joined).toContain('Note');
    expect(joined).toContain('Projects');
    expect(joined).toContain('Notes');
    expect(joined).toContain('Rotary Joint Testing System');
    // The rich note rendered into the Notes cell.
    expect(joined).toContain('Won first place');
  });

  it('builds the worksheet without an image when no logo is provided', () => {
    const workbook = new ExcelJS.Workbook();
    buildProjectsWorksheet(workbook, [row], {title: 'No Logo'}, null);
    expect(workbook.getWorksheet('Projects')?.getImages()).toHaveLength(0);
  });
});

describe('loadI2gLogoAsset', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns null when the logo fetch is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: false}));
    expect(await loadI2gLogoAsset()).toBeNull();
  });

  it('returns null when the logo fetch throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
    expect(await loadI2gLogoAsset()).toBeNull();
  });

  it('decodes the logo into base64 + bytes on success', async () => {
    const bytes = new Uint8Array([137, 80, 78, 71]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: true, arrayBuffer: async () => bytes.buffer}));

    const asset = await loadI2gLogoAsset();

    expect(asset).not.toBeNull();
    expect(asset?.extension).toBe('png');
    expect(asset?.bytes).toHaveLength(4);
    expect(asset?.dataUrl.startsWith('data:image/png;base64,')).toBe(true);
  });
});

describe('exportProjectRowsPdf', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    pdfTextCalls.length = 0;
  });

  it('draws the header, sections, and a per-project block with Notes first', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: false})); // logo load fails -> null

    await exportProjectRowsPdf([row], 'past-projects', {title: 'PDF Title', note: 'Owner note'});

    const drawnText = pdfTextCalls.join('|');
    expect(drawnText).toContain('PDF Title');
    expect(drawnText).toContain('Innovate to Grow Past Projects');
    expect(drawnText).toContain('Note');
    expect(drawnText).toContain('Projects');
    // Per-project block: title bar + Notes-first field labels.
    expect(drawnText).toContain('Project 1: Rotary Joint Testing System');
    expect(drawnText).toContain('Notes: ');
    expect(drawnText).toContain('Abstract: ');
    // Notes label is drawn before the Abstract label (Notes-first ordering).
    expect(pdfTextCalls.indexOf('Notes: ')).toBeLessThan(pdfTextCalls.indexOf('Abstract: '));
    // The rich note text is rendered (token by token).
    expect(drawnText).toContain('Won');
  });
});
