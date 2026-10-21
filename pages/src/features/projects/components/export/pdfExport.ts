import type {jsPDF} from 'jspdf';

import {
  ACCENT_GOLD_RGB,
  BRAND_BLUE_RGB,
  MUTED_TEXT_RGB,
  TABLE_ALT_FILL_RGB,
  TEXT_COLOR_RGB,
  normalizeProjectRowsExportContext,
  toDisplayValue,
  type ProjectGridRow,
  type ProjectRowsExportContext,
} from './exportTypes';
import {parseRichTextRuns, type StyledRun} from './exportRichText';
import {drawRunLine, wrapRunsToLines} from './pdfRichText';
import {loadI2gLogoAsset} from './logoAsset';
import type {ExportLogoAsset} from './exportTypes';

const LABEL_RGB = BRAND_BLUE_RGB;
const ALT_FILL_RGB = TABLE_ALT_FILL_RGB;

// Fields shown per project, in the same order as the on-screen expanded row detail.
const detailFieldsFor = (row: ProjectGridRow): Array<{label: string; value: string}> => [
  {label: 'Year-Semester', value: toDisplayValue(row.semester_label) || 'N/A'},
  {
    label: 'Class / Team#',
    value: [toDisplayValue(row.class_code), toDisplayValue(row.team_number)].filter(Boolean).join(' / ') || 'N/A',
  },
  {label: 'Team Name', value: toDisplayValue(row.team_name) || 'N/A'},
  {label: 'Organization', value: toDisplayValue(row.organization) || 'N/A'},
  {label: 'Industry', value: toDisplayValue(row.industry) || 'N/A'},
  {label: 'Student Names', value: toDisplayValue(row.student_names) || 'N/A'},
  {label: 'Abstract', value: toDisplayValue(row.abstract) || 'N/A'},
];

const MARGIN = 14;
const HEADER_BOTTOM_Y = 32;
// One self-contained block per project: a brand title bar (always visible white text on blue),
// then label/value lines on an alternating tint. Every line is page-break aware, so no project
// — including the last — is ever dropped, and headings/fills always render.
const FIELD_FONT = 9;
const FIELD_LINE = FIELD_FONT * 0.5;
const LABEL_GAP = 1.5;
const BLOCK_PADDING = 3;
const TITLE_BAR_HEIGHT = 9;

/** The document being written and where the next line goes. */
interface PdfPage {
  pdf: jsPDF;
  logo: ExportLogoAsset | null;
  title: string;
  pageWidth: number;
  pageHeight: number;
  contentWidth: number;
  cursorY: number;
}

const setBrandTextColor = (pdf: jsPDF) => pdf.setTextColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
const setBodyTextColor = (pdf: jsPDF) => pdf.setTextColor(TEXT_COLOR_RGB[0], TEXT_COLOR_RGB[1], TEXT_COLOR_RGB[2]);

/** Logo, title (at most two lines) and site name over the gold rule, repeated on every page. */
const drawPageHeader = ({pdf, logo, title, pageWidth, contentWidth}: PdfPage) => {
  const logoSize = 16;
  const titleX = logo ? MARGIN + logoSize + 7 : MARGIN;
  const titleWidth = contentWidth - (logo ? logoSize + 7 : 0);

  if (logo) {
    pdf.addImage(logo.dataUrl, 'PNG', MARGIN, 8, logoSize, logoSize);
  }

  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(14);
  setBrandTextColor(pdf);
  const titleLines = (pdf.splitTextToSize(title, titleWidth) as string[]).slice(0, 2);
  pdf.text(titleLines, titleX, 14);

  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(8);
  pdf.setTextColor(MUTED_TEXT_RGB[0], MUTED_TEXT_RGB[1], MUTED_TEXT_RGB[2]);
  pdf.text('Innovate to Grow Past Projects', titleX, titleLines.length > 1 ? 25 : 21);

  // The gold rule the site draws under page headers and table headings.
  pdf.setDrawColor(ACCENT_GOLD_RGB[0], ACCENT_GOLD_RGB[1], ACCENT_GOLD_RGB[2]);
  pdf.setLineWidth(0.8);
  pdf.line(MARGIN, HEADER_BOTTOM_Y, pageWidth - MARGIN, HEADER_BOTTOM_Y);
  pdf.setLineWidth(0.2);
  setBodyTextColor(pdf);
};

/** Start a new page (with its header) when the next `heightNeeded` would run past the bottom margin. */
const ensureSpace = (page: PdfPage, heightNeeded: number) => {
  if (page.cursorY + heightNeeded > page.pageHeight - MARGIN) {
    page.pdf.addPage();
    drawPageHeader(page);
    page.cursorY = HEADER_BOTTOM_Y + 8;
  }
};

// Draw the share note's styled runs (bold/italic/underline/highlight), wrapped to the page width.
const addRichText = (page: PdfPage, runs: StyledRun[], fontSize: number, lineHeight: number) => {
  for (const line of wrapRunsToLines(page.pdf, runs, page.contentWidth, fontSize)) {
    ensureSpace(page, lineHeight);
    drawRunLine(page.pdf, line, MARGIN, page.cursorY, fontSize);
    page.cursorY += lineHeight;
  }
};

const addSectionHeading = (page: PdfPage, label: string) => {
  const {pdf} = page;
  ensureSpace(page, 12);
  pdf.setFillColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
  pdf.rect(MARGIN, page.cursorY - 2, page.contentWidth, 8, 'F');
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(10);
  pdf.setTextColor(255, 255, 255);
  pdf.text(label, MARGIN + 3, page.cursorY + 3.5);
  page.cursorY += 12;
  setBodyTextColor(pdf);
};

/** One "Label: value" field, the value wrapped and aligned just past the bold label. */
const drawField = (page: PdfPage, field: {label: string; value: string}, tinted: boolean) => {
  const {pdf} = page;
  const valueIndent = MARGIN + BLOCK_PADDING;
  const valueWidth = page.contentWidth - BLOCK_PADDING * 2;
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(FIELD_FONT);
  const labelText = `${field.label}: `;
  const labelWidth = pdf.getTextWidth(labelText);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(FIELD_FONT);
  const wrapped = pdf.splitTextToSize(field.value, valueWidth - labelWidth) as string[];
  const lines = wrapped.length ? wrapped : [''];

  lines.forEach((line, lineIndex) => {
    ensureSpace(page, FIELD_LINE + LABEL_GAP);
    // Row tint behind the line for readability (alternates per project).
    if (tinted) {
      pdf.setFillColor(ALT_FILL_RGB[0], ALT_FILL_RGB[1], ALT_FILL_RGB[2]);
      pdf.rect(MARGIN, page.cursorY, page.contentWidth, FIELD_LINE + LABEL_GAP, 'F');
    }
    const baselineY = page.cursorY + FIELD_FONT * 0.4;
    if (lineIndex === 0) {
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(FIELD_FONT);
      pdf.setTextColor(LABEL_RGB[0], LABEL_RGB[1], LABEL_RGB[2]);
      pdf.text(labelText, valueIndent, baselineY);
    }
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(FIELD_FONT);
    setBodyTextColor(pdf);
    pdf.text(line || ' ', valueIndent + labelWidth, baselineY);
    page.cursorY += FIELD_LINE + LABEL_GAP;
  });
};

const drawProjectBlock = (page: PdfPage, row: ProjectGridRow, index: number) => {
  const {pdf} = page;
  // Title bar.
  ensureSpace(page, TITLE_BAR_HEIGHT + FIELD_LINE * 2);
  pdf.setFillColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
  pdf.rect(MARGIN, page.cursorY, page.contentWidth, TITLE_BAR_HEIGHT, 'F');
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(10);
  pdf.setTextColor(255, 255, 255);
  const titleText = `Project ${index + 1}: ${toDisplayValue(row.project_title) || 'N/A'}`;
  const titleWidth = page.contentWidth - BLOCK_PADDING * 2;
  pdf.text((pdf.splitTextToSize(titleText, titleWidth) as string[])[0], MARGIN + BLOCK_PADDING, page.cursorY + 6);
  page.cursorY += TITLE_BAR_HEIGHT;

  for (const field of detailFieldsFor(row)) {
    drawField(page, field, index % 2 === 1);
  }
  // Spacing before the next project.
  page.cursorY += 2;
};

export const exportProjectRowsPdf = async (
  rows: ProjectGridRow[],
  fileBaseName: string,
  context: ProjectRowsExportContext = {},
) => {
  const [{jsPDF: JsPdf}, logo] = await Promise.all([import('jspdf'), loadI2gLogoAsset()]);
  const exportContext = normalizeProjectRowsExportContext(context);
  const pdf: jsPDF = new JsPdf({orientation: 'landscape'});
  const pageWidth = pdf.internal.pageSize.getWidth();
  const page: PdfPage = {
    pdf,
    logo,
    title: exportContext.title,
    pageWidth,
    pageHeight: pdf.internal.pageSize.getHeight(),
    contentWidth: pageWidth - MARGIN * 2,
    cursorY: HEADER_BOTTOM_Y + 8,
  };

  drawPageHeader(page);

  const noteRuns = parseRichTextRuns(exportContext.note);
  if (noteRuns.length) {
    addSectionHeading(page, 'Note');
    addRichText(page, noteRuns, 9, 4.7);
    page.cursorY += 5;
  }

  addSectionHeading(page, 'Projects');
  rows.forEach((row, index) => drawProjectBlock(page, row, index));

  pdf.save(`${fileBaseName}.pdf`);
};
