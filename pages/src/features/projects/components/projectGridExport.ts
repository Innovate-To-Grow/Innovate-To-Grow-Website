import {PROJECT_GRID_COLUMNS, type ProjectGridRow} from './projectGrid';

const EXPORT_COLUMNS = [
  'Year-Semester',
  'Class',
  'Team#',
  'Team Name',
  'Project Title',
  'Organization',
  'Industry',
  'Abstract',
  'Student Names',
] as const;

const toExportRows = (rows: ProjectGridRow[]): (string | number)[][] =>
  rows.map((row) => [
    row.semester_label,
    row.class_code,
    row.team_number,
    row.team_name,
    row.project_title,
    row.organization,
    row.industry,
    row.abstract,
    row.student_names,
  ]);

const triggerDownload = (blob: Blob, fileName: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const escapeCsvCell = (value: string | number) => {
  const str = String(value ?? '');
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
};

export const exportProjectRowsCsv = async (rows: ProjectGridRow[], fileBaseName: string) => {
  const lines = [EXPORT_COLUMNS.map(escapeCsvCell).join(',')];
  for (const row of toExportRows(rows)) {
    lines.push(row.map(escapeCsvCell).join(','));
  }
  // Prepend UTF-8 BOM so Excel opens the file with correct encoding.
  const blob = new Blob(['\uFEFF', lines.join('\r\n')], {type: 'text/csv;charset=utf-8'});
  triggerDownload(blob, `${fileBaseName}.csv`);
};

export const exportProjectRowsExcel = async (rows: ProjectGridRow[], fileBaseName: string) => {
  const ExcelJS = (await import('exceljs')).default;
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Projects');
  worksheet.addRow(EXPORT_COLUMNS as unknown as string[]);
  for (const row of toExportRows(rows)) {
    worksheet.addRow(row);
  }
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  triggerDownload(blob, `${fileBaseName}.xlsx`);
};

export const exportProjectRowsPdf = async (rows: ProjectGridRow[], fileBaseName: string, title: string) => {
  const {jsPDF} = await import('jspdf');
  const autoTable = (await import('jspdf-autotable')).default;

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
