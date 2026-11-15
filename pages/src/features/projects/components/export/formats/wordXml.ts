import {BRAND_BLUE, HIGHLIGHT_FILL, toDisplayValue, type ProjectGridRow} from '../support/exportTypes';
import {type StyledRun} from '../richText/exportRichText';
import {escapeXml, sanitizeXmlText} from '../support/xml';

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

export const wordParagraph = (
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

export const wordSectionHeading = (text: string) =>
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

export const wordRichParagraph = (runs: StyledRun[], size: number, spacingAfter: number) =>
  `<w:p><w:pPr><w:spacing w:after="${spacingAfter}"/></w:pPr>${styledRunsToWord(runs, size)}</w:p>`;

export const wordLogoParagraph = (relationshipId: string) => {
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
export const COLUMN_PCT = [10, 6, 6, 12, 15, 12, 10, 18, 11];

export const headerCell = (label: string, widthPct: number) =>
  `<w:tc><w:tcPr><w:tcW w:w="${widthPct * 50}" w:type="pct"/><w:shd w:fill="${BRAND_BLUE}"/></w:tcPr>` +
  `<w:p>${wordRun(label, {bold: true, color: 'FFFFFF', size: 16})}</w:p></w:tc>`;

const plainCell = (value: string, widthPct: number) =>
  `<w:tc><w:tcPr><w:tcW w:w="${widthPct * 50}" w:type="pct"/></w:tcPr>` +
  `<w:p>${wordRun(toDisplayValue(value), {size: 16})}</w:p></w:tc>`;

export const projectTableRow = (row: ProjectGridRow) => {
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
