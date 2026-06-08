import ExcelJS from 'exceljs';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  buildProjectsWorksheet,
  createPdfProjectTableBody,
  createProjectRowsCsvText,
  createProjectRowsWordBlob,
  loadI2gLogoAsset,
  splitExcelText,
} from './projectGridExport';
import type {ProjectGridRow} from './projectGrid';

// jspdf/autotable are heavy and DOM/canvas-bound; mock them so we can assert the document
// assembly wiring (sections drawn, per-project table body) without rendering a real PDF.
const pdfTextCalls = vi.hoisted(() => [] as string[]);
const autoTableMock = vi.hoisted(() => vi.fn());

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
    splitTextToSize(text: string) {
      return [text];
    }
    text(value: string | string[]) {
      pdfTextCalls.push(...(Array.isArray(value) ? value : [value]));
    }
  }
  return {jsPDF: MockJsPdf};
});

vi.mock('jspdf-autotable', () => ({default: autoTableMock}));

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
};

const logo = {
  base64: 'iVBORw0KGgo=',
  bytes: Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]),
  dataUrl: 'data:image/png;base64,iVBORw0KGgo=',
  extension: 'png' as const,
};

describe('projectGridExport', () => {
  it('adds project detail rows to PDF project tables', () => {
    const body = createPdfProjectTableBody([row]);
    const detailCell = (body[1] as Array<{colSpan: number; content: string}>)[0];

    expect(body[0]).toContain('Rotary Joint Testing System');
    expect(detailCell).toMatchObject({
      colSpan: 7,
      content: expect.stringContaining('Project Detail\nAbstract: A detailed abstract with <special> characters & project context.'),
    });
    expect(detailCell).toMatchObject({
      content: expect.stringContaining('Student Names: Alice Calderon, Bob Lee'),
    });
  });

  it('includes edited project detail text before CSV project rows', () => {
    const csv = createProjectRowsCsvText([row], {
      detailsText: '<strong>Edited Past Projects Detail</strong><br><mark>Highlighted project detail & owner edits</mark>',
      title: 'Saved Merged Results',
    });

    expect(csv).toContain('Innovate to Grow Past Projects\r\nI2G Logo,');
    expect(csv).toMatch(/I2G Logo,\S*\/assets\/images\/i2glogo\.png/);
    expect(csv).toContain('Title,Saved Merged Results');
    expect(csv).toContain('Past Projects Detail\r\nEdited Past Projects Detail\r\nHighlighted project detail & owner edits');
    expect(csv).toContain('\r\nProjects\r\nYear-Semester,Class,Team#,Team Name,Project Title');
    expect(csv).toContain('A detailed abstract with <special> characters & project context.');
  });

  it('neutralizes leading formula characters in CSV cells to prevent CSV injection', () => {
    const csv = createProjectRowsCsvText(
      [
        {
          ...row,
          project_title: '=HYPERLINK("http://evil","click")',
          organization: '+1-800-EVIL',
          student_names: '@SUM(A1:A9)',
          team_name: '-2+3',
        },
      ],
      {
        title: '=cmd|\'/c calc\'!A1',
        detailsText: '=1+1 danger',
      },
    );

    // Title and detail lines starting with = are prefixed with a quote, then CSV-quoted
    // because they also contain a comma / quote where applicable.
    expect(csv).toContain("'=cmd");
    expect(csv).toContain("'=1+1 danger");
    // Project columns are neutralized too (quoted because they contain commas/quotes).
    expect(csv).toContain('"\'=HYPERLINK(""http://evil"",""click"")"');
    expect(csv).toContain("'+1-800-EVIL");
    expect(csv).toContain("'@SUM(A1:A9)");
    expect(csv).toContain("'-2+3");
    // No raw formula cell survives at the start of a field.
    expect(csv).not.toMatch(/(^|,)=HYPERLINK/m);
    expect(csv).not.toMatch(/(^|,)@SUM/m);
  });

  it('falls back to generated detail text for CSV exports when no edited detail text is provided', () => {
    const csv = createProjectRowsCsvText([row]);

    expect(csv).toContain('Past Projects Detail');
    expect(csv).toContain('Project 1');
    expect(csv).toContain('Students: Alice Calderon, Bob Lee');
    expect(csv).toContain('Abstract: A detailed abstract with <special> characters & project context.');
  });

  it('creates a real docx package for Word exports', async () => {
    const blob = createProjectRowsWordBlob(
      [row],
      {
        title: 'Shared Results',
        note: 'Owner note & review instructions',
        detailsText: '<strong>Edited Past Projects Detail</strong><br><mark>Highlighted project detail & owner edits</mark>',
      },
      logo,
    );

    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document');

    const bytes = new Uint8Array(await blob.arrayBuffer());
    expect(String.fromCharCode(...bytes.slice(0, 2))).toBe('PK');

    const packageText = new TextDecoder().decode(bytes);
    expect(packageText).toContain('[Content_Types].xml');
    expect(packageText).toContain('word/document.xml');
    expect(packageText).toContain('word/_rels/document.xml.rels');
    expect(packageText).toContain('word/media/i2g-logo.png');
    expect(packageText).toContain('rIdLogo');
    expect(packageText).toContain('Shared Results');
    expect(packageText).toContain('Owner note &amp; review instructions');
    expect(packageText).toContain('Past Projects Detail');
    expect(packageText).toContain('Edited Past Projects Detail');
    expect(packageText).toContain('Highlighted project detail &amp; owner edits');
    expect(packageText).toContain('A detailed abstract with &lt;special&gt; characters &amp; project context.');
  });

  it('falls back to generated detail text when a shared export has no saved detail text', async () => {
    const blob = createProjectRowsWordBlob([row], {
      title: 'Shared Results',
      note: '',
    });

    const packageText = new TextDecoder().decode(new Uint8Array(await blob.arrayBuffer()));

    expect(packageText).toContain('Past Projects Detail');
    expect(packageText).toContain('Project 1');
    expect(packageText).toContain('Students: Alice Calderon, Bob Lee');
    expect(packageText).toContain('Abstract: A detailed abstract with &lt;special&gt; characters &amp; project context.');
  });

  it('omits the logo parts from the Word package when no logo is provided', async () => {
    const blob = createProjectRowsWordBlob([row], {title: 'No Logo Export'});
    const packageText = new TextDecoder().decode(new Uint8Array(await blob.arrayBuffer()));

    expect(packageText).not.toContain('rIdLogo');
    expect(packageText).not.toContain('word/media/i2g-logo.png');
    expect(packageText).not.toContain('Extension="png"');
    // The rest of the document still renders.
    expect(packageText).toContain('No Logo Export');
    expect(packageText).toContain('Rotary Joint Testing System');
  });
});

describe('splitExcelText', () => {
  it('returns the text unchanged when it is under the limit', () => {
    expect(splitExcelText('short detail', 100)).toEqual(['short detail']);
  });

  it('splits at a paragraph break when the text exceeds the limit', () => {
    const block = `${'a'.repeat(50)}\n\n${'b'.repeat(50)}`;
    const chunks = splitExcelText(block, 60);

    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.join('')).toContain('a'.repeat(50));
    expect(chunks.every((chunk) => chunk.length <= 60)).toBe(true);
  });

  it('hard-splits text with no break points at the max length', () => {
    const chunks = splitExcelText('x'.repeat(150), 50);

    expect(chunks).toHaveLength(3);
    expect(chunks.every((chunk) => chunk.length === 50)).toBe(true);
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
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ok: true, arrayBuffer: async () => bytes.buffer}),
    );

    const asset = await loadI2gLogoAsset();

    expect(asset).not.toBeNull();
    expect(asset?.extension).toBe('png');
    expect(asset?.bytes).toHaveLength(4);
    expect(asset?.dataUrl.startsWith('data:image/png;base64,')).toBe(true);
  });
});

describe('buildProjectsWorksheet', () => {
  it('builds a branded worksheet with the detail section, project rows, and embedded logo', () => {
    const workbook = new ExcelJS.Workbook();
    buildProjectsWorksheet(
      workbook,
      [row],
      {title: 'Excel Title', note: 'Owner note', detailsText: '<b>Edited</b> detail text'},
      logo,
    );

    const worksheet = workbook.getWorksheet('Projects');
    expect(worksheet).toBeDefined();
    expect(worksheet?.getCell(1, 2).value).toBe('Excel Title');
    expect(worksheet?.getCell(2, 2).value).toBe('Innovate to Grow Past Projects');
    expect(worksheet?.getImages()).toHaveLength(1);

    const cellText: string[] = [];
    worksheet?.eachRow((sheetRow) => sheetRow.eachCell((cell) => cellText.push(String(cell.value ?? ''))));
    const joined = cellText.join('|');
    expect(joined).toContain('Note');
    expect(joined).toContain('Past Projects Detail');
    expect(joined).toContain('Edited detail text');
    expect(joined).toContain('Projects');
    expect(joined).toContain('Rotary Joint Testing System');
  });

  it('builds the worksheet without an image when no logo is provided', () => {
    const workbook = new ExcelJS.Workbook();
    buildProjectsWorksheet(workbook, [row], {title: 'No Logo'}, null);

    expect(workbook.getWorksheet('Projects')?.getImages()).toHaveLength(0);
  });
});

describe('exportProjectRowsPdf', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    autoTableMock.mockClear();
    pdfTextCalls.length = 0;
  });

  it('draws the sections and passes the per-project table body to autoTable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: false})); // logo load fails -> null
    const {exportProjectRowsPdf} = await import('./projectGridExport');

    await exportProjectRowsPdf([row], 'past-projects', {
      title: 'PDF Title',
      note: 'Owner note',
      detailsText: 'Detail line one',
    });

    expect(autoTableMock).toHaveBeenCalledTimes(1);
    const config = autoTableMock.mock.calls[0][1] as {head: string[][]; body: unknown[]};
    expect(config.head[0]).toContain('Year-Semester');
    expect(config.body).toHaveLength(2); // one main row + one detail row per project
    const drawnText = pdfTextCalls.join('|');
    expect(drawnText).toContain('PDF Title');
    expect(drawnText).toContain('Note');
    expect(drawnText).toContain('Past Projects Detail');
    expect(drawnText).toContain('Projects');
  });
});
