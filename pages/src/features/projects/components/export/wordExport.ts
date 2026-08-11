import {
  BRAND_BLUE,
  EXPORT_COLUMNS,
  HIGHLIGHT_FILL,
  normalizeProjectRowsExportContext,
  toDisplayValue,
  triggerDownload,
  type ExportLogoAsset,
  type ProjectGridRow,
  type ProjectRowsExportContext,
} from './exportTypes';
import {parseRichTextRuns, type StyledRun} from './exportRichText';
import {escapeXml, sanitizeXmlText} from './xml';
import {createStoredZip} from './zip';
import {loadI2gLogoAsset} from './logoAsset';

interface WordRunOptions {
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  highlight?: boolean;
  color?: string;
  size?: number;
}

const runProperties = (options: WordRunOptions) =>
  [
    options.bold ? '<w:b/>' : '',
    options.italic ? '<w:i/>' : '',
    options.underline ? '<w:u w:val="single"/>' : '',
    // <w:highlight> only allows named colors, so shade the run with our amber fill instead.
    options.highlight ? `<w:shd w:val="clear" w:color="auto" w:fill="${HIGHLIGHT_FILL}"/>` : '',
    options.color ? `<w:color w:val="${options.color}"/>` : '',
    options.size ? `<w:sz w:val="${options.size}"/>` : '',
  ].join('');

const wordRun = (text: string, options: WordRunOptions = {}) => {
  const properties = runProperties(options);
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

/** Render the share note's styled runs as Word runs, preserving bold/italic/underline/highlight. */
const styledRunsToWord = (runs: StyledRun[], size: number) =>
  runs
    .map((run) =>
      wordRun(run.text, {
        bold: run.bold,
        italic: run.italic,
        underline: run.underline,
        highlight: run.highlight,
        size,
      }),
    )
    .join('');

const wordRichParagraph = (runs: StyledRun[], size: number, spacingAfter: number) =>
  `<w:p><w:pPr><w:spacing w:after="${spacingAfter}"/></w:pPr>${styledRunsToWord(runs, size)}</w:p>`;

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

// Header cells get more weight on the wide, multi-line Abstract column.
const COLUMN_PCT = [10, 6, 6, 12, 15, 12, 10, 18, 11];

const headerCell = (label: string, widthPct: number) =>
  `<w:tc><w:tcPr><w:tcW w:w="${widthPct * 50}" w:type="pct"/><w:shd w:fill="${BRAND_BLUE}"/></w:tcPr>` +
  `<w:p>${wordRun(label, {bold: true, color: 'FFFFFF', size: 16})}</w:p></w:tc>`;

const plainCell = (value: string, widthPct: number) =>
  `<w:tc><w:tcPr><w:tcW w:w="${widthPct * 50}" w:type="pct"/></w:tcPr>` +
  `<w:p>${wordRun(toDisplayValue(value), {size: 16})}</w:p></w:tc>`;

const projectTableRow = (row: ProjectGridRow) => {
  const cells = [
    plainCell(row.semester_label, COLUMN_PCT[0]),
    plainCell(row.class_code, COLUMN_PCT[1]),
    plainCell(row.team_number, COLUMN_PCT[2]),
    plainCell(row.team_name, COLUMN_PCT[3]),
    plainCell(row.project_title, COLUMN_PCT[4]),
    plainCell(row.organization, COLUMN_PCT[5]),
    plainCell(row.industry, COLUMN_PCT[6]),
    plainCell(row.abstract, COLUMN_PCT[7]),
    plainCell(row.student_names, COLUMN_PCT[8]),
  ].join('');
  return `<w:tr>${cells}</w:tr>`;
};

export const createProjectRowsWordBlob = (
  rows: ProjectGridRow[],
  context: ProjectRowsExportContext = {},
  logo: ExportLogoAsset | null = null,
) => {
  const exportContext = normalizeProjectRowsExportContext(context);
  const headerRow = `<w:tr>${EXPORT_COLUMNS.map((label, index) => headerCell(label, COLUMN_PCT[index])).join('')}</w:tr>`;
  const bodyRows = rows.map(projectTableRow).join('');
  const noteRuns = parseRichTextRuns(exportContext.note);

  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    ${logo ? wordLogoParagraph('rIdLogo') : ''}
    ${wordParagraph(exportContext.title, {alignment: 'center', bold: true, color: BRAND_BLUE, size: 32, spacingAfter: 80})}
    ${wordParagraph('Innovate to Grow Past Projects', {
      alignment: 'center',
      bold: true,
      color: '53657A',
      size: 20,
      spacingAfter: 220,
    })}
    ${noteRuns.length ? `${wordSectionHeading('Note')}${wordRichParagraph(noteRuns, 20, 180)}` : ''}
    ${wordSectionHeading('Projects')}
    <w:tbl>
      <w:tblPr>
        <w:tblW w:w="5000" w:type="pct"/>
        <w:tblLayout w:type="fixed"/>
        <w:tblBorders>
          <w:top w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:left w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:bottom w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:right w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:insideH w:val="single" w:sz="4" w:color="D7DDE7"/>
          <w:insideV w:val="single" w:sz="4" w:color="D7DDE7"/>
        </w:tblBorders>
      </w:tblPr>
      ${headerRow}
      ${bodyRows}
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
  <dc:title>${escapeXml(exportContext.title)}</dc:title>
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

export const exportProjectRowsWord = async (
  rows: ProjectGridRow[],
  fileBaseName: string,
  context: ProjectRowsExportContext = {},
) => {
  const logo = await loadI2gLogoAsset();
  const blob = createProjectRowsWordBlob(rows, context, logo);
  triggerDownload(blob, `${fileBaseName}.docx`);
};
