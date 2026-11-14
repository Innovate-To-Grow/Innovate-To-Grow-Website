import type {Workbook, Worksheet} from 'exceljs';
import {
    normalizeProjectRowsExportContext,
    triggerDownload,
    type ExportLogoAsset,
    type ProjectGridRow,
    type ProjectRowsExportContext,
} from '../support/exportTypes';
import {loadI2gLogoAsset} from '../support/logoAsset';
import {addNoteSection, addProjectsTable, addTitleBlock, COLUMN_WIDTHS} from './excelSheet';

export const buildProjectsWorksheet = (
  workbook: Workbook,
  rows: ProjectGridRow[],
  context: ProjectRowsExportContext = {},
  logo: ExportLogoAsset | null = null,
): Worksheet => {
  const worksheet = workbook.addWorksheet('Projects');
  const exportContext = normalizeProjectRowsExportContext(context);
  worksheet.columns = COLUMN_WIDTHS.map((width) => ({width}));

  addTitleBlock(workbook, worksheet, exportContext, rows.length, logo);
  worksheet.addRow([]);
  addNoteSection(worksheet, exportContext.note);
  addProjectsTable(worksheet, rows);
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
