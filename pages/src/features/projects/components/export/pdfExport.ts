import type {jsPDF} from 'jspdf';

import {
  BRAND_BLUE_RGB,
  normalizeProjectRowsExportContext,
  toDisplayValue,
  type ProjectGridRow,
  type ProjectRowsExportContext,
} from './exportTypes';
import {parseRichTextRuns, type StyledRun} from './exportRichText';
import {drawRunLine, wrapRunsToLines} from './pdfRichText';
import {loadI2gLogoAsset} from './logoAsset';

const LABEL_RGB: [number, number, number] = [15, 45, 82];
const ALT_FILL_RGB: [number, number, number] = [247, 250, 252];
const CARD_BORDER_RGB: [number, number, number] = [189, 211, 234];

const plainRuns = (text: string): StyledRun[] => (text ? [{text}] : []);

// Fields shown per project, Notes first (matching the on-screen order), then the standard fields.
const detailFieldsFor = (row: ProjectGridRow): Array<{label: string; runs: StyledRun[]}> => {
  const noteRuns = parseRichTextRuns(row.curation ?? '');
  return [
    {label: 'Notes', runs: noteRuns.length ? noteRuns : plainRuns('N/A')},
    {label: 'Year-Semester', runs: plainRuns(toDisplayValue(row.semester_label) || 'N/A')},
    {
      label: 'Class / Team#',
      runs: plainRuns(
        [toDisplayValue(row.class_code), toDisplayValue(row.team_number)].filter(Boolean).join(' / ') || 'N/A',
      ),
    },
    {label: 'Team Name', runs: plainRuns(toDisplayValue(row.team_name) || 'N/A')},
    {label: 'Organization', runs: plainRuns(toDisplayValue(row.organization) || 'N/A')},
    {label: 'Industry', runs: plainRuns(toDisplayValue(row.industry) || 'N/A')},
    {label: 'Student Names', runs: plainRuns(toDisplayValue(row.student_names) || 'N/A')},
    {label: 'Abstract', runs: plainRuns(toDisplayValue(row.abstract) || 'N/A')},
  ];
};

export const exportProjectRowsPdf = async (
  rows: ProjectGridRow[],
  fileBaseName: string,
  context: ProjectRowsExportContext = {},
) => {
  const [{jsPDF: JsPdf}, logo] = await Promise.all([import('jspdf'), loadI2gLogoAsset()]);
  const exportContext = normalizeProjectRowsExportContext(context);
  const pdf: jsPDF = new JsPdf({orientation: 'landscape'});
  const margin = 14;
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const contentWidth = pageWidth - margin * 2;
  const headerBottomY = 32;
  let cursorY = headerBottomY + 8;

  const setBrandTextColor = () => pdf.setTextColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
  const setBodyTextColor = () => pdf.setTextColor(32, 54, 77);

  const drawPageHeader = () => {
    const logoSize = 16;
    const titleX = logo ? margin + logoSize + 7 : margin;
    const titleWidth = contentWidth - (logo ? logoSize + 7 : 0);

    if (logo) {
      pdf.addImage(logo.dataUrl, 'PNG', margin, 8, logoSize, logoSize);
    }

    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(14);
    setBrandTextColor();
    const titleLines = (pdf.splitTextToSize(exportContext.title, titleWidth) as string[]).slice(0, 2);
    pdf.text(titleLines, titleX, 14);

    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    pdf.setTextColor(83, 101, 122);
    pdf.text('Innovate to Grow Past Projects', titleX, titleLines.length > 1 ? 25 : 21);

    pdf.setDrawColor(CARD_BORDER_RGB[0], CARD_BORDER_RGB[1], CARD_BORDER_RGB[2]);
    pdf.line(margin, headerBottomY, pageWidth - margin, headerBottomY);
    setBodyTextColor();
  };

  const ensureSpace = (heightNeeded: number) => {
    if (cursorY + heightNeeded > pageHeight - margin) {
      pdf.addPage();
      drawPageHeader();
      cursorY = headerBottomY + 8;
    }
  };

  const addWrappedText = (text: string, fontSize: number, lineHeight: number) => {
    pdf.setFontSize(fontSize);
    pdf.setFont('helvetica', 'normal');
    setBodyTextColor();
    for (const paragraph of (text || ' ').split(/\r\n|\r|\n/)) {
      if (!paragraph.trim()) {
        ensureSpace(lineHeight);
        cursorY += lineHeight;
        continue;
      }
      for (const line of pdf.splitTextToSize(paragraph, contentWidth) as string[]) {
        ensureSpace(lineHeight);
        pdf.text(line || ' ', margin, cursorY);
        cursorY += lineHeight;
      }
    }
  };

  const addSectionHeading = (label: string) => {
    ensureSpace(12);
    pdf.setFillColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
    pdf.rect(margin, cursorY - 2, contentWidth, 8, 'F');
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(10);
    pdf.setTextColor(255, 255, 255);
    pdf.text(label, margin + 3, cursorY + 3.5);
    cursorY += 12;
    setBodyTextColor();
  };

  // One self-contained block per project: a brand title bar (always visible white text on blue),
  // then label/value lines on an alternating tint. Every line is page-break aware, so no project
  // — including the last — is ever dropped, and headings/fills always render.
  const FIELD_FONT = 9;
  const FIELD_LINE = FIELD_FONT * 0.5;
  const LABEL_GAP = 1.5;
  const BLOCK_PADDING = 3;
  const TITLE_BAR_HEIGHT = 9;

  const drawProjectBlock = (row: ProjectGridRow, index: number) => {
    const fields = detailFieldsFor(row);
    const valueIndent = margin + BLOCK_PADDING;
    const valueWidth = contentWidth - BLOCK_PADDING * 2;

    // Title bar.
    ensureSpace(TITLE_BAR_HEIGHT + FIELD_LINE * 2);
    pdf.setFillColor(BRAND_BLUE_RGB[0], BRAND_BLUE_RGB[1], BRAND_BLUE_RGB[2]);
    pdf.rect(margin, cursorY, contentWidth, TITLE_BAR_HEIGHT, 'F');
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(10);
    pdf.setTextColor(255, 255, 255);
    const titleText = `Project ${index + 1}: ${toDisplayValue(row.project_title) || 'N/A'}`;
    pdf.text((pdf.splitTextToSize(titleText, contentWidth - BLOCK_PADDING * 2) as string[])[0], valueIndent, cursorY + 6);
    cursorY += TITLE_BAR_HEIGHT;

    for (const field of fields) {
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(FIELD_FONT);
      const labelText = `${field.label}: `;
      const labelWidth = pdf.getTextWidth(labelText);
      const lines = wrapRunsToLines(pdf, field.runs, valueWidth - labelWidth, FIELD_FONT);

      lines.forEach((line, lineIndex) => {
        ensureSpace(FIELD_LINE + LABEL_GAP);
        // Row tint behind the line for readability (alternates per project).
        if (index % 2 === 1) {
          pdf.setFillColor(ALT_FILL_RGB[0], ALT_FILL_RGB[1], ALT_FILL_RGB[2]);
          pdf.rect(margin, cursorY, contentWidth, FIELD_LINE + LABEL_GAP, 'F');
        }
        const baselineY = cursorY + FIELD_FONT * 0.4;
        if (lineIndex === 0) {
          pdf.setFont('helvetica', 'bold');
          pdf.setFontSize(FIELD_FONT);
          pdf.setTextColor(LABEL_RGB[0], LABEL_RGB[1], LABEL_RGB[2]);
          pdf.text(labelText, valueIndent, baselineY);
        }
        // Value (and its wrapped continuation lines) align just past the bold label.
        drawRunLine(pdf, line, valueIndent + labelWidth, baselineY, FIELD_FONT);
        cursorY += FIELD_LINE + LABEL_GAP;
      });
    }

    // Block border + spacing before the next project.
    cursorY += 2;
  };

  drawPageHeader();

  if (exportContext.note) {
    addSectionHeading('Note');
    addWrappedText(exportContext.note, 9, 4.7);
    cursorY += 5;
  }

  addSectionHeading('Projects');
  rows.forEach((row, index) => drawProjectBlock(row, index));

  pdf.save(`${fileBaseName}.pdf`);
};
