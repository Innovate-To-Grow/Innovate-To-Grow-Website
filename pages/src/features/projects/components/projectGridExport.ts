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

interface ExportLogoAsset {
  base64: string;
  bytes: Uint8Array;
  dataUrl: string;
  extension: 'png';
}

const I2G_LOGO_URL = '/assets/images/i2glogo.png';
const BRAND_BLUE = '0F2D52';
const BRAND_BLUE_RGB = [15, 45, 82] as const;
const BORDER_BLUE = 'BDD3EA';
const LIGHT_BLUE = 'EAF4FF';
const TABLE_ALT_FILL = 'F7FAFC';
const DETAIL_SEPARATOR_PATTERN = /\n\s*-{10,}\s*\n/g;

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

const splitProjectDetailBlocks = (text: string) => text.split(DETAIL_SEPARATOR_PATTERN).map((block) => block.trim()).filter(Boolean);

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

const bytesToBase64 = (bytes: Uint8Array) => {
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.slice(index, index + chunkSize));
  }
  return btoa(binary);
};

const loadI2gLogoAsset = async (): Promise<ExportLogoAsset | null> => {
  if (typeof fetch === 'undefined') {
    return null;
  }

  try {
    const response = await fetch(I2G_LOGO_URL);
    if (!response.ok) {
      return null;
    }

    const bytes = new Uint8Array(await response.arrayBuffer());
    const base64 = bytesToBase64(bytes);
    return {
      base64,
      bytes,
      dataUrl: `data:image/png;base64,${base64}`,
      extension: 'png',
    };
  } catch {
    return null;
  }
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

const createStoredZip = (files: Array<{name: string; content: string | Uint8Array}>) => {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  files.forEach((file) => {
    const nameBytes = textEncoder.encode(file.name);
    const contentBytes = typeof file.content === 'string' ? textEncoder.encode(file.content) : file.content;
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
  const [ExcelJS, logo] = await Promise.all([import('exceljs').then((module) => module.default), loadI2gLogoAsset()]);
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Projects');
  const sharedContext = normalizeSharedExportContext(context);
  const projectDetailsText = getSharedProjectDetailsText(rows, sharedContext.detailsText);

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

  worksheet.addRow([]);
  worksheet.addRow([]);
  worksheet.addRow([]);
  worksheet.getRow(1).height = 28;
  worksheet.getRow(2).height = 22;
  worksheet.getRow(3).height = 18;

  for (let rowNumber = 1; rowNumber <= 3; rowNumber += 1) {
    for (let columnNumber = 1; columnNumber <= EXPORT_COLUMNS.length; columnNumber += 1) {
      const cell = worksheet.getCell(rowNumber, columnNumber);
      cell.fill = {type: 'pattern', pattern: 'solid', fgColor: {argb: LIGHT_BLUE}};
    }
  }

  if (logo) {
    const imageId = workbook.addImage({base64: logo.dataUrl, extension: logo.extension});
    worksheet.addImage(imageId, {
      ext: {height: 58, width: 58},
      tl: {col: 0.15, row: 0.1},
    });
  }

  worksheet.mergeCells(1, 2, 1, EXPORT_COLUMNS.length);
  worksheet.mergeCells(2, 2, 2, EXPORT_COLUMNS.length);
  worksheet.mergeCells(3, 2, 3, EXPORT_COLUMNS.length);

  worksheet.getCell(1, 2).value = sharedContext.title;
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
  };

  if (sharedContext.note) {
    addSectionRow('Note');
    addMergedTextRow(sharedContext.note);
    worksheet.addRow([]);
  }

  if (projectDetailsText) {
    addSectionRow('Past Projects Detail');

    for (const detailBlock of splitProjectDetailBlocks(projectDetailsText).flatMap((block) => splitExcelText(block))) {
      addMergedTextRow(detailBlock, TABLE_ALT_FILL);
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

  for (const [index, row] of toExportRows(rows).entries()) {
    const dataRow = worksheet.addRow(row);
    dataRow.eachCell({includeEmpty: true}, (cell) => {
      cell.alignment = {vertical: 'top', wrapText: true};
      cell.border = {
        bottom: {style: 'thin', color: {argb: 'D7DDE7'}},
      };
      if (index % 2 === 1) {
        cell.fill = {type: 'pattern', pattern: 'solid', fgColor: {argb: TABLE_ALT_FILL}};
      }
    });
  }

  worksheet.autoFilter = {
    from: {column: 1, row: headerRow.number},
    to: {column: EXPORT_COLUMNS.length, row: headerRow.number},
  };

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
  const [{jsPDF}, autoTable, logo] = await Promise.all([
    import('jspdf'),
    import('jspdf-autotable').then((module) => module.default),
    loadI2gLogoAsset(),
  ]);
  const sharedContext = normalizeSharedExportContext(context);
  const projectDetailsText = getSharedProjectDetailsText(rows, sharedContext.detailsText);
  const pdf = new jsPDF({orientation: 'landscape'});
  const margin = 14;
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const textWidth = pageWidth - margin * 2;
  const headerBottomY = 32;
  let cursorY = headerBottomY + 8;

  const setBrandTextColor = () => pdf.setTextColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
  const setBodyTextColor = () => pdf.setTextColor(32, 54, 77);

  const drawPageHeader = () => {
    const logoSize = 16;
    const titleX = logo ? margin + logoSize + 7 : margin;
    const titleWidth = textWidth - (logo ? logoSize + 7 : 0);

    if (logo) {
      pdf.addImage(logo.dataUrl, 'PNG', margin, 8, logoSize, logoSize);
    }

    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(14);
    setBrandTextColor();
    const titleLines = (pdf.splitTextToSize(sharedContext.title, titleWidth) as string[]).slice(0, 2);
    pdf.text(titleLines, titleX, 14);

    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    pdf.setTextColor(83, 101, 122);
    pdf.text('Innovate to Grow Past Projects', titleX, titleLines.length > 1 ? 25 : 21);

    pdf.setDrawColor(189, 211, 234);
    pdf.line(margin, headerBottomY, pageWidth - margin, headerBottomY);
    setBodyTextColor();
  };

  const addPageIfNeeded = (heightNeeded: number) => {
    if (cursorY + heightNeeded > pageHeight - margin) {
      pdf.addPage();
      drawPageHeader();
      cursorY = headerBottomY + 8;
    }
  };

  const addWrappedText = (text: string, fontSize: number, lineHeight: number, isBold = false) => {
    pdf.setFontSize(fontSize);
    pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
    setBodyTextColor();
    for (const paragraph of (text || ' ').split(/\r\n|\r|\n/)) {
      if (!paragraph.trim()) {
        addPageIfNeeded(lineHeight);
        cursorY += lineHeight;
        continue;
      }

      const lines = pdf.splitTextToSize(paragraph, textWidth) as string[];
      for (const line of lines) {
        addPageIfNeeded(lineHeight);
        pdf.text(line || ' ', margin, cursorY);
        cursorY += lineHeight;
      }
    }
  };

  const addSectionHeading = (label: string) => {
    addPageIfNeeded(10);
    pdf.setFillColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
    pdf.rect(margin, cursorY - 2, textWidth, 8, 'F');
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(10);
    pdf.setTextColor(255, 255, 255);
    pdf.text(label, margin + 3, cursorY + 3.5);
    cursorY += 12;
    setBodyTextColor();
  };

  drawPageHeader();

  if (sharedContext.note) {
    addSectionHeading('Note');
    addWrappedText(sharedContext.note, 9, 4.7);
    cursorY += 5;
  }

  if (projectDetailsText) {
    addSectionHeading('Past Projects Detail');
    addWrappedText(projectDetailsText, 9, 4.5);
    cursorY += 5;
  }

  addSectionHeading('Projects');

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
    margin: {left: margin, right: margin, top: headerBottomY + 8},
    styles: {
      cellPadding: 2.4,
      fontSize: 8,
      overflow: 'linebreak',
      textColor: [32, 54, 77],
      valign: 'top',
    },
    alternateRowStyles: {
      fillColor: [247, 250, 252],
    },
    headStyles: {
      fillColor: [...BRAND_BLUE_RGB],
      fontStyle: 'bold',
    },
    didDrawPage: drawPageHeader,
  });

  pdf.save(`${fileBaseName}.pdf`);
};

export const exportSharedProjectRowsWord = async (
  rows: ProjectGridRow[],
  fileBaseName: string,
  context: SharedProjectExportContext,
) => {
  const logo = await loadI2gLogoAsset();
  const blob = createSharedProjectRowsWordBlob(rows, context, logo);
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

const wordParagraph = (
  text: string,
  options: {
    alignment?: 'center' | 'left';
    bold?: boolean;
    color?: string;
    shading?: string;
    size?: number;
    spacingAfter?: number;
  } = {},
) =>
  `<w:p><w:pPr><w:spacing w:after="${options.spacingAfter ?? 120}"/>${
    options.alignment ? `<w:jc w:val="${options.alignment}"/>` : ''
  }${options.shading ? `<w:shd w:fill="${options.shading}"/>` : ''}</w:pPr>${wordRun(text, options)}</w:p>`;

const wordSectionHeading = (text: string) =>
  wordParagraph(text, {bold: true, color: 'FFFFFF', shading: BRAND_BLUE, size: 22, spacingAfter: 80});

const wordLogoParagraph = (relationshipId: string) => {
  const size = 685800;
  return `<w:p>
    <w:pPr><w:jc w:val="center"/><w:spacing w:after="120"/></w:pPr>
    <w:r>
      <w:drawing>
        <wp:inline distT="0" distB="0" distL="0" distR="0">
          <wp:extent cx="${size}" cy="${size}"/>
          <wp:effectExtent l="0" t="0" r="0" b="0"/>
          <wp:docPr id="1" name="I2G Logo"/>
          <wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
          <a:graphic>
            <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
              <pic:pic>
                <pic:nvPicPr>
                  <pic:cNvPr id="0" name="i2glogo.png"/>
                  <pic:cNvPicPr/>
                </pic:nvPicPr>
                <pic:blipFill>
                  <a:blip r:embed="${relationshipId}"/>
                  <a:stretch><a:fillRect/></a:stretch>
                </pic:blipFill>
                <pic:spPr>
                  <a:xfrm>
                    <a:off x="0" y="0"/>
                    <a:ext cx="${size}" cy="${size}"/>
                  </a:xfrm>
                  <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
                </pic:spPr>
              </pic:pic>
            </a:graphicData>
          </a:graphic>
        </wp:inline>
      </w:drawing>
    </w:r>
  </w:p>`;
};

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
  logo: ExportLogoAsset | null = null,
) => {
  const sharedContext = normalizeSharedExportContext(context);
  const projectDetailsText = getSharedProjectDetailsText(rows, sharedContext.detailsText);
  const projectDetailBlocks = splitProjectDetailBlocks(projectDetailsText);
  const columnWidth = Math.floor(5000 / EXPORT_COLUMNS.length);
  const tableRows = [
    `<w:tr>${EXPORT_COLUMNS.map((column) => wordTableCell(column, {header: true, width: columnWidth})).join('')}</w:tr>`,
    ...rows.map(
      (row) =>
        `<w:tr>${toExportRows([row])[0].map((cell) => wordTableCell(String(cell ?? ''), {width: columnWidth})).join('')}</w:tr>`,
    ),
  ].join('');

  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    ${logo ? wordLogoParagraph('rIdLogo') : ''}
    ${wordParagraph(sharedContext.title, {alignment: 'center', bold: true, color: BRAND_BLUE, size: 32, spacingAfter: 80})}
    ${wordParagraph('Innovate to Grow Past Projects', {
      alignment: 'center',
      bold: true,
      color: '53657A',
      size: 20,
      spacingAfter: 220,
    })}
    ${sharedContext.note ? `${wordSectionHeading('Note')}${wordParagraph(sharedContext.note, {size: 20, spacingAfter: 180})}` : ''}
    ${wordSectionHeading('Past Projects Detail')}
    ${projectDetailBlocks
      .map((block) => wordParagraph(block, {shading: TABLE_ALT_FILL, size: 18, spacingAfter: 140}))
      .join('')}
    ${wordSectionHeading('Projects')}
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
  ${logo ? '<Default Extension="png" ContentType="image/png"/>' : ''}
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
    ...(logo
      ? [
          {
            name: 'word/_rels/document.xml.rels',
            content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdLogo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/i2g-logo.png"/>
</Relationships>`,
          },
          {
            name: 'word/media/i2g-logo.png',
            content: logo.bytes,
          },
        ]
      : []),
  ]);

  return new Blob([packageBytes], {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  });
};
