import type {jsPDF} from 'jspdf';
import {
    I2G_PDF_LOGO_URL,
    normalizeProjectRowsExportContext,
    type ProjectGridRow,
    type ProjectRowsExportContext,
} from '../support/exportTypes';
import {parseRichTextRuns} from '../richText/exportRichText';
import {fontStyle} from '../richText/pdfRichText';
import {loadI2gLogoAsset} from '../support/logoAsset';
import {loadPdfFontFiles, registerPdfTypeface, type PdfFontStyle} from '../support/pdfTypeface';
import {
    addRichText,
    addSectionHeading,
    drawPageHeader,
    drawProjectBlock,
    HEADER_BOTTOM_Y,
    MARGIN,
    type PdfPage,
} from './pdfLayout';

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
