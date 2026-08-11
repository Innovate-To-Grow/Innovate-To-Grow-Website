import type {Workbook, Worksheet} from 'exceljs';

import {
  BRAND_BLUE,
  BORDER_BLUE,
  EXPORT_COLUMNS,
  HIGHLIGHT_TEXT,
  LIGHT_BLUE,
  TABLE_ALT_FILL,
  normalizeProjectRowsExportContext,
  toDisplayValue,
  triggerDownload,
  type ExportLogoAsset,
  type ProjectGridRow,
  type ProjectRowsExportContext,
} from './exportTypes';
import {parseRichTextRuns, runsToPlainText, type StyledRun} from './exportRichText';
import {loadI2gLogoAsset} from './logoAsset';

// Per-column widths (last entry = Student Names). Abstract is wide and wraps to multiple lines.
const COLUMN_WIDTHS = [16, 12, 10, 24, 34, 28, 18, 60, 30];

// ExcelJS rich-text fragment type, kept local so the module has no value-level exceljs dependency.
interface ExcelRichTextFragment {
  text: string;
  font?: {bold?: boolean; italic?: boolean; underline?: boolean; color?: {argb: string}; size?: number};
}

/**
 * Convert the share note's styled runs to ExcelJS rich text. Bold/italic/underline map to inline
 * runs; highlight has no per-run cell fill in a single cell, so it is approximated with an amber
 * font color (documented trade-off). Returns null for an empty note.
 */
const runsToExcelRichText = (runs: StyledRun[]): {richText: ExcelRichTextFragment[]} | null => {
  if (!runs.length) {
    return null;
  }
  return {
    richText: runs.map((run) => ({
      text: run.text,
      font: {
        ...(run.bold ? {bold: true} : {}),
        ...(run.italic ? {italic: true} : {}),
        ...(run.underline ? {underline: true} : {}),
        ...(run.highlight ? {color: {argb: HIGHLIGHT_TEXT}} : {}),
        size: 11,
      },
    })),
  };
};

const estimateLineCount = (text: string, charsPerLine: number) =>
  text
    .split(/\r\n|\r|\n/)
    .reduce((total, line) => total + Math.max(1, Math.ceil((line.length || 1) / charsPerLine)), 0);

export const buildProjectsWorksheet = (
  workbook: Workbook,
  rows: ProjectGridRow[],
  context: ProjectRowsExportContext = {},
  logo: ExportLogoAsset | null = null,
): Worksheet => {
  const worksheet = workbook.addWorksheet('Projects');
  const exportContext = normalizeProjectRowsExportContext(context);

  worksheet.columns = COLUMN_WIDTHS.map((width) => ({width}));

  worksheet.addRow([]);
  worksheet.addRow([]);
  worksheet.addRow([]);
  worksheet.getRow(1).height = 28;
  worksheet.getRow(2).height = 22;
  worksheet.getRow(3).height = 18;

  for (let rowNumber = 1; rowNumber <= 3; rowNumber += 1) {
    for (let columnNumber = 1; columnNumber <= EXPORT_COLUMNS.length; columnNumber += 1) {
      worksheet.getCell(rowNumber, columnNumber).fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: {argb: LIGHT_BLUE},
      };
    }
  }

  if (logo) {
    const imageId = workbook.addImage({base64: logo.dataUrl, extension: logo.extension});
    worksheet.addImage(imageId, {ext: {height: 58, width: 58}, tl: {col: 0.15, row: 0.1}});
  }

  worksheet.mergeCells(1, 2, 1, EXPORT_COLUMNS.length);
  worksheet.mergeCells(2, 2, 2, EXPORT_COLUMNS.length);
  worksheet.mergeCells(3, 2, 3, EXPORT_COLUMNS.length);

  worksheet.getCell(1, 2).value = exportContext.title;
  worksheet.getCell(1, 2).font = {bold: true, color: {argb: BRAND_BLUE}, size: 18};
  worksheet.getCell(1, 2).alignment = {vertical: 'bottom'};

  worksheet.getCell(2, 2).value = 'Innovate to Grow Past Projects';
  worksheet.getCell(2, 2).font = {bold: true, color: {argb: BRAND_BLUE}, size: 11};
  worksheet.getCell(2, 2).alignment = {vertical: 'middle'};

  worksheet.getCell(3, 2).value = `${rows.length} project${rows.length === 1 ? '' : 's'} exported`;
  worksheet.getCell(3, 2).font = {color: {argb: '53657A'}, size: 10};
  worksheet.getCell(3, 2).alignment = {vertical: 'top'};

  worksheet.addRow([]);

  const addSectionRow = (label: string) => {
    const row = worksheet.addRow([label]);
    worksheet.mergeCells(row.number, 1, row.number, EXPORT_COLUMNS.length);
    row.height = 22;
    row.eachCell({includeEmpty: true}, (cell) => {
      cell.fill = {type: 'pattern', pattern: 'solid', fgColor: {argb: BRAND_BLUE}};
      cell.font = {bold: true, color: {argb: 'FFFFFF'}, size: 11};
      cell.alignment = {vertical: 'middle'};
    });
  };

  const addMergedTextRow = (text: string, fill = 'FFFFFF') => {
    const row = worksheet.addRow([text]);
    worksheet.mergeCells(row.number, 1, row.number, EXPORT_COLUMNS.length);
    const lineCount = text.split(/\r\n|\r|\n/).length;
    row.height = Math.min(220, Math.max(34, lineCount * 15));
    row.eachCell({includeEmpty: true}, (cell) => {
      cell.alignment = {vertical: 'top', wrapText: true};
      cell.border = {
        bottom: {style: 'thin', color: {argb: BORDER_BLUE}},
        left: {style: 'thin', color: {argb: BORDER_BLUE}},
        right: {style: 'thin', color: {argb: BORDER_BLUE}},
        top: {style: 'thin', color: {argb: BORDER_BLUE}},
      };
      cell.fill = {type: 'pattern', pattern: 'solid', fgColor: {argb: fill}};
      cell.font = {color: {argb: '20364D'}, size: 11};
    });
    return row;
  };

  // The share-level note is rich text; render it into the merged cell preserving emphasis.
  const noteRuns = parseRichTextRuns(exportContext.note);
  if (noteRuns.length) {
    addSectionRow('Note');
    const noteRow = addMergedTextRow(runsToPlainText(noteRuns));
    const richNote = runsToExcelRichText(noteRuns);
    if (richNote) {
      worksheet.getCell(noteRow.number, 1).value = richNote;
    }
    worksheet.addRow([]);
  }

  addSectionRow('Projects');
  const headerRow = worksheet.addRow(EXPORT_COLUMNS as unknown as string[]);
  headerRow.font = {bold: true};
  headerRow.eachCell((cell) => {
    cell.fill = {type: 'pattern', pattern: 'solid', fgColor: {argb: LIGHT_BLUE}};
    cell.font = {bold: true, color: {argb: BRAND_BLUE}};
    cell.alignment = {vertical: 'middle', wrapText: true};
    cell.border = {
      bottom: {style: 'thin', color: {argb: BORDER_BLUE}},
      top: {style: 'thin', color: {argb: BORDER_BLUE}},
    };
  });

  rows.forEach((row, index) => {
    const dataRow = worksheet.addRow([
      toDisplayValue(row.semester_label),
      toDisplayValue(row.class_code),
      toDisplayValue(row.team_number),
      toDisplayValue(row.team_name),
      toDisplayValue(row.project_title),
      toDisplayValue(row.organization),
      toDisplayValue(row.industry),
      toDisplayValue(row.abstract),
      toDisplayValue(row.student_names),
    ]);

    // Size the row to the wrapped Abstract cell.
    const abstractLines = estimateLineCount(toDisplayValue(row.abstract), 58);
    dataRow.height = Math.min(320, Math.max(18, abstractLines * 13));

    dataRow.eachCell({includeEmpty: true}, (cell) => {
      cell.alignment = {vertical: 'top', wrapText: true};
      cell.border = {bottom: {style: 'thin', color: {argb: 'D7DDE7'}}};
      if (index % 2 === 1) {
        cell.fill = {type: 'pattern', pattern: 'solid', fgColor: {argb: TABLE_ALT_FILL}};
      }
    });
  });

  worksheet.autoFilter = {
    from: {column: 1, row: headerRow.number},
    to: {column: EXPORT_COLUMNS.length, row: headerRow.number},
  };

  return worksheet;
};

export const exportProjectRowsExcel = async (
  rows: ProjectGridRow[],
  fileBaseName: string,
  context: ProjectRowsExportContext = {},
) => {
  const [ExcelJS, logo] = await Promise.all([import('exceljs').then((module) => module.default), loadI2gLogoAsset()]);
  const workbook = new ExcelJS.Workbook();
  buildProjectsWorksheet(workbook, rows, context, logo);
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  triggerDownload(blob, `${fileBaseName}.xlsx`);
};
