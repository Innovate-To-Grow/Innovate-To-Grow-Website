import type {jsPDF} from 'jspdf';

import {
  ACCENT_GOLD_RGB,
  BRAND_BLUE_RGB,
  I2G_PDF_LOGO_URL,
  MUTED_TEXT_RGB,
  TABLE_ALT_FILL_RGB,
  TEXT_COLOR_RGB,
  normalizeProjectRowsExportContext,
  toDisplayValue,
  type ProjectGridRow,
  type ProjectRowsExportContext,
} from '../support/exportTypes';
import {parseRichTextRuns, type StyledRun} from '../richText/exportRichText';
import {drawRunLine, fontStyle, wrapRunsToLines} from '../richText/pdfRichText';
import {loadI2gLogoAsset} from '../support/logoAsset';
import {loadPdfFontFiles, registerPdfTypeface, type PdfFontStyle, type PdfTypeface} from '../support/pdfTypeface';
import type {ExportLogoAsset} from '../support/exportTypes';

const LABEL_RGB = BRAND_BLUE_RGB;
const ALT_FILL_RGB = TABLE_ALT_FILL_RGB;

// Fields shown per project, in the same order as the on-screen expanded row detail.
const detailFieldsFor = (
  row: ProjectGridRow,
  show: (value: string) => string,
): Array<{label: string; value: string}> => [
  {label: 'Year-Semester', value: show(row.semester_label) || 'N/A'},
  {
    label: 'Class / Team#',
    value: [show(row.class_code), show(row.team_number)].filter(Boolean).join(' / ') || 'N/A',
  },
  {label: 'Team Name', value: show(row.team_name) || 'N/A'},
  {label: 'Organization', value: show(row.organization) || 'N/A'},
  {label: 'Industry', value: show(row.industry) || 'N/A'},
  {label: 'Student Names', value: show(row.student_names) || 'N/A'},
  {label: 'Abstract', value: show(row.abstract) || 'N/A'},
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
  typeface: PdfTypeface;
  logo: ExportLogoAsset | null;
  title: string;
  /** The list's name under the title ("Innovate to Grow Past Projects"). */
  heading: string;
  pageWidth: number;
  pageHeight: number;
  contentWidth: number;
  cursorY: number;
}

const setBrandTextColor = (pdf: jsPDF) => pdf.setTextColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
const setBodyTextColor = (pdf: jsPDF) => pdf.setTextColor(TEXT_COLOR_RGB[0], TEXT_COLOR_RGB[1], TEXT_COLOR_RGB[2]);

/** A row value as the page's font can draw it. */
const showValue = (page: PdfPage, value: string | number | null | undefined) =>
  page.typeface.drawable(toDisplayValue(value)).trim();

/** Logo, title (at most two lines) and heading over the gold rule, repeated on every page. */
const drawPageHeader = ({pdf, typeface, logo, title, heading, pageWidth, contentWidth}: PdfPage) => {
  const logoSize = 16;
  const titleX = logo ? MARGIN + logoSize + 7 : MARGIN;
  const titleWidth = contentWidth - (logo ? logoSize + 7 : 0);

  if (logo) {
    // One alias, so every page's header reuses the same image object.
    pdf.addImage(logo.dataUrl, 'PNG', MARGIN, 8, logoSize, logoSize, 'i2g-logo');
  }

  pdf.setFont(typeface.family, 'bold');
  pdf.setFontSize(14);
  setBrandTextColor(pdf);
  const titleLines = (pdf.splitTextToSize(title, titleWidth) as string[]).slice(0, 2);
  pdf.text(titleLines, titleX, 14);

  pdf.setFont(typeface.family, 'normal');
  pdf.setFontSize(8);
  pdf.setTextColor(MUTED_TEXT_RGB[0], MUTED_TEXT_RGB[1], MUTED_TEXT_RGB[2]);
  pdf.text(heading, titleX, titleLines.length > 1 ? 25 : 21);

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
  for (const line of wrapRunsToLines(page.pdf, runs, page.contentWidth, fontSize, page.typeface.family)) {
    ensureSpace(page, lineHeight);
    drawRunLine(page.pdf, line, MARGIN, page.cursorY, fontSize, page.typeface.family);
    page.cursorY += lineHeight;
  }
};

const addSectionHeading = (page: PdfPage, label: string) => {
  const {pdf} = page;
  ensureSpace(page, 12);
  pdf.setFillColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
  pdf.rect(MARGIN, page.cursorY - 2, page.contentWidth, 8, 'F');
  pdf.setFont(page.typeface.family, 'bold');
  pdf.setFontSize(10);
  pdf.setTextColor(255, 255, 255);
  pdf.text(label, MARGIN + 3, page.cursorY + 3.5);
  page.cursorY += 12;
  setBodyTextColor(pdf);
};

/** One "Label: value" field, the value wrapped and aligned just past the bold label. */
const drawField = (page: PdfPage, field: {label: string; value: string}, tinted: boolean) => {
  const {pdf, typeface} = page;
  const valueIndent = MARGIN + BLOCK_PADDING;
  const valueWidth = page.contentWidth - BLOCK_PADDING * 2;
  pdf.setFont(typeface.family, 'bold');
  pdf.setFontSize(FIELD_FONT);
  const labelText = `${field.label}: `;
  const labelWidth = pdf.getTextWidth(labelText);
  pdf.setFont(typeface.family, 'normal');
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
      pdf.setFont(typeface.family, 'bold');
      pdf.setFontSize(FIELD_FONT);
      pdf.setTextColor(LABEL_RGB[0], LABEL_RGB[1], LABEL_RGB[2]);
      pdf.text(labelText, valueIndent, baselineY);
    }
    pdf.setFont(typeface.family, 'normal');
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
  pdf.setFont(page.typeface.family, 'bold');
  pdf.setFontSize(10);
  pdf.setTextColor(255, 255, 255);
  const titleText = `Project ${index + 1}: ${showValue(page, row.project_title) || 'N/A'}`;
  const titleWidth = page.contentWidth - BLOCK_PADDING * 2;
  pdf.text((pdf.splitTextToSize(titleText, titleWidth) as string[])[0], MARGIN + BLOCK_PADDING, page.cursorY + 6);
  page.cursorY += TITLE_BAR_HEIGHT;

  for (const field of detailFieldsFor(row, (value) => showValue(page, value))) {
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
  const exportContext = normalizeProjectRowsExportContext(context);
  const noteRuns = parseRichTextRuns(exportContext.note);
  // Regular and bold draw the header, labels and values; the note's emphasis may need the italic faces too.
  const fontStyles: PdfFontStyle[] = [
    'normal',
    'bold',
    ...noteRuns.map((run) => fontStyle(Boolean(run.bold), Boolean(run.italic))),
  ];
  const [{jsPDF: JsPdf}, logo, fontFiles] = await Promise.all([
    import('jspdf'),
    loadI2gLogoAsset(I2G_PDF_LOGO_URL),
    loadPdfFontFiles(fontStyles),
  ]);
  // compress: Flate-encode the page content, the logo's pixels and the embedded font subsets.
  const pdf: jsPDF = new JsPdf({orientation: 'landscape', compress: true});
  const typeface = registerPdfTypeface(pdf, fontFiles);
  const pageWidth = pdf.internal.pageSize.getWidth();
  const page: PdfPage = {
    pdf,
    typeface,
    logo,
    title: typeface.drawable(exportContext.title),
    heading: typeface.drawable(exportContext.heading),
    pageWidth,
    pageHeight: pdf.internal.pageSize.getHeight(),
    contentWidth: pageWidth - MARGIN * 2,
    cursorY: HEADER_BOTTOM_Y + 8,
  };

  drawPageHeader(page);

  const drawableNote = noteRuns.map((run) => ({...run, text: typeface.drawable(run.text)}));
  if (drawableNote.some((run) => run.text.trim())) {
    addSectionHeading(page, 'Note');
    addRichText(page, drawableNote, 9, 4.7);
    page.cursorY += 5;
  }

  addSectionHeading(page, 'Projects');
  rows.forEach((row, index) => drawProjectBlock(page, row, index));

  pdf.save(`${fileBaseName}.pdf`);
};
