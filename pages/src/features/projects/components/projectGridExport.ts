import {PROJECT_GRID_COLUMNS, type ProjectGridRow} from './projectGrid';
import {createPastProjectsDetailText, pastProjectsDetailHtmlToPlainText} from './pastProjectsDetailText';

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

interface SharedProjectExportContext {
  detailsText?: string;
  note?: string;
  title: string;
}

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

const toDisplayValue = (value: string | number | null | undefined) => String(value ?? '').trim();

const sanitizeXmlText = (value: string | number | null | undefined) =>
  Array.from(toDisplayValue(value))
    .filter((character) => {
      const code = character.charCodeAt(0);
      return code === 0x09 || code === 0x0a || code === 0x0d || code >= 0x20;
    })
    .join('');

const escapeXml = (value: string | number | null | undefined) =>
  sanitizeXmlText(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const normalizeSharedExportContext = ({detailsText, note, title}: SharedProjectExportContext) => ({
  detailsText: pastProjectsDetailHtmlToPlainText(detailsText ?? '').trim(),
  note: (note ?? '').trim(),
  title: title.trim() || 'Shared Past Project Results',
});

const getSharedProjectDetailsText = (rows: ProjectGridRow[], detailsText: string) =>
  detailsText || createPastProjectsDetailText(rows).trim();

const splitExcelText = (text: string, maxLength = 30000) => {
  const chunks: string[] = [];
  let remaining = text;

  while (remaining.length > maxLength) {
    let splitAt = remaining.lastIndexOf('\n\n', maxLength);
    if (splitAt < maxLength / 2) {
      splitAt = remaining.lastIndexOf('\n', maxLength);
    }
    if (splitAt < 1) {
      splitAt = maxLength;
    }

    chunks.push(remaining.slice(0, splitAt).trimEnd());
    remaining = remaining.slice(splitAt).trimStart();
  }

  if (remaining) {
    chunks.push(remaining);
  }

  return chunks;
};

const textEncoder = new TextEncoder();

const crcTable = Array.from({length: 256}, (_, index) => {
  let value = index;
  for (let bit = 0; bit < 8; bit += 1) {
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  }
  return value >>> 0;
});

const getCrc32 = (data: Uint8Array) => {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
};

const writeUint16 = (target: Uint8Array, offset: number, value: number) => {
  target[offset] = value & 0xff;
  target[offset + 1] = (value >>> 8) & 0xff;
};

const writeUint32 = (target: Uint8Array, offset: number, value: number) => {
  target[offset] = value & 0xff;
  target[offset + 1] = (value >>> 8) & 0xff;
  target[offset + 2] = (value >>> 16) & 0xff;
  target[offset + 3] = (value >>> 24) & 0xff;
};

const concatBytes = (parts: Uint8Array[]) => {
  const totalLength = parts.reduce((total, part) => total + part.length, 0);
  const output = new Uint8Array(totalLength);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
};

const createStoredZip = (files: Array<{name: string; content: string}>) => {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  files.forEach((file) => {
    const nameBytes = textEncoder.encode(file.name);
    const contentBytes = textEncoder.encode(file.content);
    const crc = getCrc32(contentBytes);

    const localHeader = new Uint8Array(30 + nameBytes.length);
    writeUint32(localHeader, 0, 0x04034b50);
    writeUint16(localHeader, 4, 20);
    writeUint16(localHeader, 6, 0);
    writeUint16(localHeader, 8, 0);
    writeUint16(localHeader, 10, 0);
    writeUint16(localHeader, 12, 0);
    writeUint32(localHeader, 14, crc);
    writeUint32(localHeader, 18, contentBytes.length);
    writeUint32(localHeader, 22, contentBytes.length);
    writeUint16(localHeader, 26, nameBytes.length);
    writeUint16(localHeader, 28, 0);
    localHeader.set(nameBytes, 30);

    localParts.push(localHeader, contentBytes);

    const centralHeader = new Uint8Array(46 + nameBytes.length);
    writeUint32(centralHeader, 0, 0x02014b50);
    writeUint16(centralHeader, 4, 20);
    writeUint16(centralHeader, 6, 20);
    writeUint16(centralHeader, 8, 0);
    writeUint16(centralHeader, 10, 0);
    writeUint16(centralHeader, 12, 0);
    writeUint16(centralHeader, 14, 0);
    writeUint32(centralHeader, 16, crc);
    writeUint32(centralHeader, 20, contentBytes.length);
    writeUint32(centralHeader, 24, contentBytes.length);
    writeUint16(centralHeader, 28, nameBytes.length);
    writeUint16(centralHeader, 30, 0);
    writeUint16(centralHeader, 32, 0);
    writeUint16(centralHeader, 34, 0);
    writeUint16(centralHeader, 36, 0);
    writeUint32(centralHeader, 38, 0);
    writeUint32(centralHeader, 42, offset);
    centralHeader.set(nameBytes, 46);
    centralParts.push(centralHeader);

    offset += localHeader.length + contentBytes.length;
  });

  const centralDirectory = concatBytes(centralParts);
  const endRecord = new Uint8Array(22);
  writeUint32(endRecord, 0, 0x06054b50);
  writeUint16(endRecord, 4, 0);
  writeUint16(endRecord, 6, 0);
  writeUint16(endRecord, 8, files.length);
  writeUint16(endRecord, 10, files.length);
  writeUint32(endRecord, 12, centralDirectory.length);
  writeUint32(endRecord, 16, offset);
  writeUint16(endRecord, 20, 0);

  return concatBytes([...localParts, centralDirectory, endRecord]);
};

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

export const exportSharedProjectRowsExcel = async (
  rows: ProjectGridRow[],
  fileBaseName: string,
  context: SharedProjectExportContext,
) => {
  const ExcelJS = (await import('exceljs')).default;
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Projects');
  const sharedContext = normalizeSharedExportContext(context);
  const projectDetailsText = getSharedProjectDetailsText(rows, sharedContext.detailsText);

  const titleRow = worksheet.addRow([sharedContext.title]);
  worksheet.mergeCells(titleRow.number, 1, titleRow.number, EXPORT_COLUMNS.length);
  titleRow.font = {bold: true, size: 16};

  const noteRow = worksheet.addRow(['Notes', sharedContext.note]);
  worksheet.mergeCells(noteRow.number, 2, noteRow.number, EXPORT_COLUMNS.length);
  noteRow.font = {size: 11};
  worksheet.getCell(noteRow.number, 1).font = {bold: true};

  worksheet.addRow([]);
  if (projectDetailsText) {
    const detailHeadingRow = worksheet.addRow(['Past Projects Detail']);
    worksheet.mergeCells(detailHeadingRow.number, 1, detailHeadingRow.number, EXPORT_COLUMNS.length);
    detailHeadingRow.font = {bold: true, size: 12};

    for (const detailChunk of splitExcelText(projectDetailsText)) {
      const detailRow = worksheet.addRow([detailChunk]);
      worksheet.mergeCells(detailRow.number, 1, detailRow.number, EXPORT_COLUMNS.length);
      detailRow.font = {size: 11};
    }

    worksheet.addRow([]);
  }

  const headerRow = worksheet.addRow(EXPORT_COLUMNS as unknown as string[]);
  headerRow.font = {bold: true};

  for (const row of toExportRows(rows)) {
    worksheet.addRow(row);
  }

  worksheet.columns = [
    {width: 16},
    {width: 12},
    {width: 10},
    {width: 24},
    {width: 34},
    {width: 28},
    {width: 18},
    {width: 72},
    {width: 42},
  ];

  worksheet.eachRow((row) => {
    row.alignment = {vertical: 'top', wrapText: true};
  });

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

export const exportSharedProjectRowsPdf = async (
  rows: ProjectGridRow[],
  fileBaseName: string,
  context: SharedProjectExportContext,
) => {
  const {jsPDF} = await import('jspdf');
  const autoTable = (await import('jspdf-autotable')).default;
  const sharedContext = normalizeSharedExportContext(context);
  const projectDetailsText = getSharedProjectDetailsText(rows, sharedContext.detailsText);
  const pdf = new jsPDF({orientation: 'landscape'});
  const margin = 14;
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const textWidth = pageWidth - margin * 2;
  let cursorY = 16;

  const addPageIfNeeded = (heightNeeded: number) => {
    if (cursorY + heightNeeded > pageHeight - margin) {
      pdf.addPage();
      cursorY = margin;
    }
  };

  const addWrappedText = (text: string, fontSize: number, lineHeight: number, isBold = false) => {
    pdf.setFontSize(fontSize);
    pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
    const lines = pdf.splitTextToSize(text || ' ', textWidth) as string[];
    for (const line of lines) {
      addPageIfNeeded(lineHeight);
      pdf.text(line || ' ', margin, cursorY);
      cursorY += lineHeight;
    }
  };

  addWrappedText(sharedContext.title, 16, 7, true);
  cursorY += 2;
  addWrappedText(`Notes: ${sharedContext.note}`, 10, 5);
  cursorY += 4;

  if (projectDetailsText) {
    addWrappedText('Past Projects Detail', 12, 6, true);
    cursorY += 1;
    addWrappedText(projectDetailsText, 9, 4.5);
    cursorY += 4;
  }

  autoTable(pdf, {
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
    startY: cursorY,
    styles: {
      fontSize: 8,
      cellPadding: 2,
      overflow: 'linebreak',
    },
    headStyles: {
      fillColor: [15, 45, 82],
    },
  });

  pdf.save(`${fileBaseName}.pdf`);
};

export const exportSharedProjectRowsWord = async (
  rows: ProjectGridRow[],
  fileBaseName: string,
  context: SharedProjectExportContext,
) => {
  const blob = createSharedProjectRowsWordBlob(rows, context);
  triggerDownload(blob, `${fileBaseName}.docx`);
};

const wordRun = (text: string, options: {bold?: boolean; color?: string; size?: number} = {}) => {
  const properties = [
    options.bold ? '<w:b/>' : '',
    options.color ? `<w:color w:val="${options.color}"/>` : '',
    options.size ? `<w:sz w:val="${options.size}"/>` : '',
  ].join('');
  const escapedLines = sanitizeXmlText(text).split(/\r\n|\r|\n/).map(escapeXml);
  const textNodes = escapedLines
    .map((line, index) => `${index > 0 ? '<w:br/>' : ''}<w:t xml:space="preserve">${line}</w:t>`)
    .join('');
  return `<w:r>${properties ? `<w:rPr>${properties}</w:rPr>` : ''}${textNodes}</w:r>`;
};

const wordParagraph = (text: string, options: {bold?: boolean; color?: string; size?: number; spacingAfter?: number} = {}) =>
  `<w:p><w:pPr><w:spacing w:after="${options.spacingAfter ?? 120}"/></w:pPr>${wordRun(text, options)}</w:p>`;

const wordTableCell = (text: string, options: {header?: boolean; width?: number} = {}) =>
  `<w:tc><w:tcPr>${options.width ? `<w:tcW w:w="${options.width}" w:type="pct"/>` : ''}${
    options.header ? '<w:shd w:fill="0F2D52"/>' : ''
  }</w:tcPr><w:p>${wordRun(text, {
    bold: options.header,
    color: options.header ? 'FFFFFF' : undefined,
    size: options.header ? 18 : 17,
  })}</w:p></w:tc>`;

export const createSharedProjectRowsWordBlob = (
  rows: ProjectGridRow[],
  context: SharedProjectExportContext,
) => {
  const sharedContext = normalizeSharedExportContext(context);
  const projectDetailsText = getSharedProjectDetailsText(rows, sharedContext.detailsText);
  const columnWidth = Math.floor(5000 / EXPORT_COLUMNS.length);
  const tableRows = [
    `<w:tr>${EXPORT_COLUMNS.map((column) => wordTableCell(column, {header: true, width: columnWidth})).join('')}</w:tr>`,
    ...rows.map(
      (row) =>
        `<w:tr>${toExportRows([row])[0].map((cell) => wordTableCell(String(cell ?? ''), {width: columnWidth})).join('')}</w:tr>`,
    ),
  ].join('');

  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    ${wordParagraph(sharedContext.title, {bold: true, color: '0F2D52', size: 32, spacingAfter: 160})}
    ${wordParagraph('Notes', {bold: true, color: '0F2D52', size: 20, spacingAfter: 40})}
    ${wordParagraph(sharedContext.note, {size: 20, spacingAfter: 180})}
    ${wordParagraph('Past Projects Detail', {bold: true, color: '0F2D52', size: 24, spacingAfter: 100})}
    ${wordParagraph(projectDetailsText, {size: 18, spacingAfter: 180})}
    ${wordParagraph('Projects', {bold: true, color: '0F2D52', size: 24, spacingAfter: 100})}
    <w:tbl>
      <w:tblPr>
        <w:tblW w:w="5000" w:type="pct"/>
        <w:tblBorders>
          <w:top w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:left w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:bottom w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:right w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:insideH w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:insideV w:val="single" w:sz="4" w:color="D7DDE7"/>
        </w:tblBorders>
      </w:tblPr>
      ${tableRows}
    </w:tbl>
    <w:sectPr>
      <w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/>
      <w:pgMar w:top="720" w:right="720" w:bottom="720" w:left="720" w:header="360" w:footer="360" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>`;

  const packageBytes = createStoredZip([
    {
      name: '[Content_Types].xml',
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`,
    },
    {
      name: '_rels/.rels',
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>`,
    },
    {
      name: 'docProps/app.xml',
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Innovate to Grow Website</Application>
</Properties>`,
    },
    {
      name: 'docProps/core.xml',
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>${escapeXml(sharedContext.title)}</dc:title>
  <dc:creator>Innovate to Grow Website</dc:creator>
</cp:coreProperties>`,
    },
    {
      name: 'word/document.xml',
      content: documentXml,
    },
  ]);

  return new Blob([packageBytes], {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  });
};
