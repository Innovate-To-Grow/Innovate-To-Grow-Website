import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const exportMocks = vi.hoisted(() => {
  const autoTable = vi.fn();
  const pdfSave = vi.fn();
  const pdfAddImage = vi.fn();
  const objectUrl = 'blob:project-export';
  const createObjectURL = vi.fn(() => objectUrl);
  const revokeObjectURL = vi.fn();
  const clickedDownloads: string[] = [];
  const workbooks: FakeWorkbook[] = [];

  class FakeRow {
    number: number;
    height = 0;
    font: unknown;
    values: unknown[];

    constructor(number: number, values: unknown[]) {
      this.number = number;
      this.values = values;
    }

    eachCell(_optionsOrCallback: unknown, maybeCallback?: (cell: Record<string, unknown>) => void) {
      const callback = typeof _optionsOrCallback === 'function'
        ? _optionsOrCallback as (cell: Record<string, unknown>) => void
        : maybeCallback;
      if (!callback) return;
      Array.from({length: 9}, () => ({})).forEach((cell) => callback(cell));
    }
  }

  class FakeWorksheet {
    rows: FakeRow[] = [];
    cells = new Map<string, Record<string, unknown>>();
    columns: unknown[] = [];
    autoFilter: unknown;
    mergeCells = vi.fn();
    addImage = vi.fn();

    addRow(values: unknown[] = []) {
      const row = new FakeRow(this.rows.length + 1, values);
      this.rows.push(row);
      return row;
    }

    getRow(rowNumber: number) {
      while (this.rows.length < rowNumber) {
        this.addRow([]);
      }
      return this.rows[rowNumber - 1];
    }

    getCell(rowNumber: number, columnNumber: number) {
      const key = `${rowNumber}:${columnNumber}`;
      if (!this.cells.has(key)) {
        this.cells.set(key, {});
      }
      return this.cells.get(key) as Record<string, unknown>;
    }
  }

  class FakeWorkbook {
    worksheet = new FakeWorksheet();
    addImage = vi.fn(() => 7);
    xlsx = {
      writeBuffer: vi.fn(async () => new Uint8Array([1, 2, 3]).buffer),
    };

    constructor() {
      workbooks.push(this);
    }

    addWorksheet() {
      return this.worksheet;
    }
  }

  return {
    autoTable,
    clickedDownloads,
    createObjectURL,
    FakeWorkbook,
    objectUrl,
    pdfAddImage,
    pdfSave,
    revokeObjectURL,
    workbooks,
  };
});

vi.mock('exceljs', () => ({
  default: {
    Workbook: exportMocks.FakeWorkbook,
  },
}));

vi.mock('jspdf', () => ({
  jsPDF: vi.fn(function jsPDFMock() {
    return {
    addImage: exportMocks.pdfAddImage,
    addPage: vi.fn(),
    internal: {
      pageSize: {
        getHeight: () => 210,
        getWidth: () => 297,
      },
    },
    line: vi.fn(),
    rect: vi.fn(),
    save: exportMocks.pdfSave,
    setDrawColor: vi.fn(),
    setFillColor: vi.fn(),
    setFont: vi.fn(),
    setFontSize: vi.fn(),
    setTextColor: vi.fn(),
    splitTextToSize: vi.fn((text: string) => text.split(/\s+/).reduce<string[]>((lines, word) => {
      const last = lines[lines.length - 1] ?? '';
      if (!last || `${last} ${word}`.length > 24) {
        lines.push(word);
      } else {
        lines[lines.length - 1] = `${last} ${word}`;
      }
      return lines;
    }, [])),
    text: vi.fn(),
    };
  }),
}));

vi.mock('jspdf-autotable', () => ({
  default: exportMocks.autoTable,
}));

import {
  createPdfProjectTableBody,
  createProjectRowsCsvText,
  createProjectRowsWordBlob,
  exportProjectRowsCsv,
  exportProjectRowsExcel,
  exportProjectRowsPdf,
  exportProjectRowsWord,
} from '@/features/projects/components/projectGridExport';
import type {ProjectGridRow} from '@/features/projects/components/projectGrid';

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
  beforeEach(() => {
    vi.clearAllMocks();
    exportMocks.clickedDownloads.length = 0;
    exportMocks.workbooks.length = 0;
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => Uint8Array.from([137, 80, 78, 71]).buffer,
    })));
    vi.stubGlobal('URL', {
      createObjectURL: exportMocks.createObjectURL,
      revokeObjectURL: exportMocks.revokeObjectURL,
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function click(this: HTMLAnchorElement) {
      exportMocks.clickedDownloads.push(this.download);
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

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

    expect(csv).toContain('Innovate to Grow Past Projects\r\nI2G Logo,/assets/images/i2glogo.png');
    expect(csv).toContain('Title,Saved Merged Results');
    expect(csv).toContain('Past Projects Detail\r\nEdited Past Projects Detail\r\nHighlighted project detail & owner edits');
    expect(csv).toContain('\r\nProjects\r\nYear-Semester,Class,Team#,Team Name,Project Title');
    expect(csv).toContain('A detailed abstract with <special> characters & project context.');
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

  it('downloads CSV and Word blobs with the requested file names', async () => {
    await exportProjectRowsCsv([row], 'projects-export', {
      note: 'CSV note',
    });
    await exportProjectRowsWord([row], 'projects-export', {
      title: 'Word export',
    });

    expect(exportMocks.clickedDownloads).toEqual(['projects-export.csv', 'projects-export.docx']);
    expect(exportMocks.createObjectURL).toHaveBeenCalledTimes(2);
    expect(exportMocks.revokeObjectURL).toHaveBeenCalledWith(exportMocks.objectUrl);
  });

  it('builds an Excel workbook with logo, detail text, filters, and a download', async () => {
    await exportProjectRowsExcel([row], 'projects-export', {
      detailsText: 'Detail block one\n\n------------\n\nDetail block two',
      note: 'Excel note',
      title: 'Excel export',
    });

    const workbook = exportMocks.workbooks[0];
    expect(workbook.addImage).toHaveBeenCalledWith({
      base64: 'data:image/png;base64,iVBORw==',
      extension: 'png',
    });
    expect(workbook.worksheet.rows.some((excelRow) => excelRow.values.includes('Note'))).toBe(true);
    expect(workbook.worksheet.rows.some((excelRow) => excelRow.values.includes('Past Projects Detail'))).toBe(true);
    expect(workbook.worksheet.rows.some((excelRow) => excelRow.values.includes('Projects'))).toBe(true);
    expect(workbook.worksheet.autoFilter).toBeTruthy();
    expect(exportMocks.clickedDownloads).toEqual(['projects-export.xlsx']);
  });

  it('builds a PDF export with auto table rows and saves the requested file name', async () => {
    await exportProjectRowsPdf([row], 'projects-export', {
      detailsText: 'Detailed text',
      note: 'PDF note',
      title: 'PDF export',
    });

    expect(exportMocks.autoTable).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        body: createPdfProjectTableBody([row]),
        head: [expect.arrayContaining(['Year-Semester', 'Project Title'])],
      }),
    );
    expect(exportMocks.pdfAddImage).toHaveBeenCalled();
    expect(exportMocks.pdfSave).toHaveBeenCalledWith('projects-export.pdf');
  });
});
