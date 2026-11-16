import {
    BRAND_BLUE,
    MUTED_TEXT,
    EXPORT_COLUMNS,
    normalizeProjectRowsExportContext,
    triggerDownload,
    type ExportLogoAsset,
    type ProjectGridRow,
    type ProjectRowsExportContext,
} from '../support/exportTypes';
import {parseRichTextRuns} from '../richText/exportRichText';
import {escapeXml} from '../support/xml';
import {createStoredZip} from '../support/zip';
import {loadI2gLogoAsset} from '../support/logoAsset';
import {
    COLUMN_PCT,
    headerCell,
    projectTableRow,
    wordLogoParagraph,
    wordParagraph,
    wordRichParagraph,
    wordSectionHeading,
} from './wordXml';

const buildDocumentXml = (
  rows: ProjectGridRow[],
  exportContext: ReturnType<typeof normalizeProjectRowsExportContext>,
  logo: ExportLogoAsset | null,
) => {
  const headerRow = `<w:tr>${EXPORT_COLUMNS.map((label, index) => headerCell(label, COLUMN_PCT[index])).join('')}</w:tr>`;
  const bodyRows = rows.map(projectTableRow).join('');
  const noteRuns = parseRichTextRuns(exportContext.note);

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    ${logo ? wordLogoParagraph('rIdLogo') : ''}
    ${wordParagraph(exportContext.title, {alignment: 'center', bold: true, color: BRAND_BLUE, size: 32, spacingAfter: 80})}
    ${wordParagraph(exportContext.heading, {
      alignment: 'center',
      bold: true,
      color: MUTED_TEXT,
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
};

const contentTypesXml = (hasLogo: boolean) => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  ${hasLogo ? '<Default Extension="png" ContentType="image/png"/>' : ''}
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`;

const PACKAGE_RELS_XML = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>`;

const APP_PROPERTIES_XML = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Innovate to Grow Website</Application>
</Properties>`;

const coreProperties = (title: string) => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>${escapeXml(title)}</dc:title>
  <dc:creator>Innovate to Grow Website</dc:creator>
</cp:coreProperties>`;

const LOGO_RELS_XML = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdLogo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/i2g-logo.png"/>
</Relationships>`;

/** The .docx package parts around the document: content types, relationships, properties, the logo. */
const packageParts = (documentXml: string, title: string, logo: ExportLogoAsset | null) => [
  {name: '[Content_Types].xml', content: contentTypesXml(Boolean(logo))},
  {name: '_rels/.rels', content: PACKAGE_RELS_XML},
  {name: 'docProps/app.xml', content: APP_PROPERTIES_XML},
  {name: 'docProps/core.xml', content: coreProperties(title)},
  {name: 'word/document.xml', content: documentXml},
  ...(logo
    ? [
        {name: 'word/_rels/document.xml.rels', content: LOGO_RELS_XML},
        {name: 'word/media/i2g-logo.png', content: logo.bytes},
      ]
    : []),
];

export const createProjectRowsWordBlob = (
  rows: ProjectGridRow[],
  context: ProjectRowsExportContext = {},
  logo: ExportLogoAsset | null = null,
) => {
  const exportContext = normalizeProjectRowsExportContext(context);
  const documentXml = buildDocumentXml(rows, exportContext, logo);
  const packageBytes = createStoredZip(packageParts(documentXml, exportContext.title, logo));

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
