import type {jsPDF} from 'jspdf';

import {fetchBinaryAsset} from './binaryAsset';
import {createGlyphFallback, hasWinAnsiGlyph} from './glyphFallback';

export type PdfFontStyle = 'normal' | 'bold' | 'italic' | 'bolditalic';

/** The font family every text call of one PDF uses, and the fold that keeps text within its glyphs. */
export interface PdfTypeface {
  family: string;
  drawable: (text: string) => string;
}

export type PdfFontFiles = Array<{style: PdfFontStyle; base64: string}>;

// Open Sans, the site's body font, embedded so names and abstracts print as the site shows them: jsPDF's built-in
// fonts only encode Windows-1252. The files are Google Fonts' static Open Sans 3.003 instances with hinting and the
// OpenType layout tables removed (jsPDF uses neither); license in public/assets/fonts/open-sans/OFL.txt.
const OPEN_SANS = 'OpenSans';
const OPEN_SANS_DIR = '/assets/fonts/open-sans/';
const OPEN_SANS_FILES: Record<PdfFontStyle, string> = {
  normal: 'OpenSans-Regular.ttf',
  bold: 'OpenSans-Bold.ttf',
  italic: 'OpenSans-Italic.ttf',
  bolditalic: 'OpenSans-BoldItalic.ttf',
};

/** A TrueType outline font starts with version 1.0, which tells it apart from an HTML error page. */
const isTrueType = (bytes: Uint8Array) =>
  bytes.length > 4 && bytes[0] === 0 && bytes[1] === 1 && bytes[2] === 0 && bytes[3] === 0;

/** Fetch the Open Sans faces a document draws with. Null when any is unavailable: the PDF then uses Helvetica. */
export const loadPdfFontFiles = async (styles: Iterable<PdfFontStyle>): Promise<PdfFontFiles | null> => {
  const wanted = [...new Set(styles)];
  const assets = await Promise.all(wanted.map((style) => fetchBinaryAsset(OPEN_SANS_DIR + OPEN_SANS_FILES[style])));
  const files: PdfFontFiles = [];
  for (const [index, asset] of assets.entries()) {
    if (!asset || !isTrueType(asset.bytes)) {
      return null;
    }
    files.push({style: wanted[index], base64: asset.base64});
  }
  return files;
};

const helvetica = (): PdfTypeface => ({family: 'helvetica', drawable: createGlyphFallback(hasWinAnsiGlyph)});

/** Embed the fetched faces in the document; without them (or if jsPDF cannot read one) fall back to Helvetica. */
export const registerPdfTypeface = (pdf: jsPDF, files: PdfFontFiles | null): PdfTypeface => {
  if (!files) {
    return helvetica();
  }
  try {
    const faces = files.map(({style, base64}) => {
      pdf.addFileToVFS(OPEN_SANS_FILES[style], base64);
      pdf.addFont(OPEN_SANS_FILES[style], OPEN_SANS, style);
      pdf.setFont(OPEN_SANS, style);
      // jsPDF's parsed TrueType font: glyph 0 is .notdef, i.e. no glyph for that character.
      return pdf.getFont().metadata as {characterToGlyph: (codePoint: number) => number};
    });
    const hasGlyph = (codePoint: number) => faces.every((face) => face.characterToGlyph(codePoint) !== 0);
    // jsPDF logs a font it cannot parse instead of throwing, so check that every face maps a plain letter.
    return hasGlyph(0x41) ? {family: OPEN_SANS, drawable: createGlyphFallback(hasGlyph)} : helvetica();
  } catch {
    return helvetica();
  }
};
