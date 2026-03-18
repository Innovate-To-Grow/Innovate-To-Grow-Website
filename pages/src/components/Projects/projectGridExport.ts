import {jsPDF} from 'jspdf';
import autoTable from 'jspdf-autotable';
import {utils, writeFile} from 'xlsx';
import {PROJECT_GRID_COLUMNS, type ProjectGridRow} from './projectGrid';

const toExportRows = (rows: ProjectGridRow[]) =>
  rows.map((row) => ({
    'Year-Semester': row.semester_label,
    Class: row.class_code,
    'Team#': row.team_number,
    'Team Name': row.team_name,
    'Project Title': row.project_title,
    Organization: row.organization,
    Industry: row.industry,
    Abstract: row.abstract,
    'Student Names': row.student_names,
  }));

export const exportProjectRowsCsv = (rows: ProjectGridRow[], fileBaseName: string) => {
  const worksheet = utils.json_to_sheet(toExportRows(rows));
  const workbook = utils.book_new();
  utils.book_append_sheet(workbook, worksheet, 'Projects');
  writeFile(workbook, `${fileBaseName}.csv`, {bookType: 'csv'});
};

export const exportProjectRowsExcel = (rows: ProjectGridRow[], fileBaseName: string) => {
  const worksheet = utils.json_to_sheet(toExportRows(rows));
  const workbook = utils.book_new();
  utils.book_append_sheet(workbook, worksheet, 'Projects');
  writeFile(workbook, `${fileBaseName}.xlsx`, {bookType: 'xlsx'});
};

export const exportProjectRowsPdf = (rows: ProjectGridRow[], fileBaseName: string, title: string) => {
  const document = new jsPDF({orientation: 'landscape'});

  document.setFontSize(16);
  document.text(title, 14, 16);

  autoTable(document, {
    head: [PROJECT_GRID_COLUMNS.map((column) => column.label)],
    body: rows.map((row) => [
      row.semester_label,
      row.class_code,
      row.team_number,
      row.team_name,
      row.project_title,
      row.organization,
      row.industry,
    ]),
    startY: 24,
    styles: {
      fontSize: 8,
      cellPadding: 2,
      overflow: 'linebreak',
    },
    headStyles: {
      fillColor: [15, 45, 82],
    },
  });

  document.save(`${fileBaseName}.pdf`);
};
