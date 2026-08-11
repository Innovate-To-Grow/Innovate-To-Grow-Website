import type {jsPDF} from 'jspdf';

import type {StyledRun} from './exportRichText';

const HIGHLIGHT_RGB: [number, number, number] = [255, 243, 163];
const TEXT_RGB: [number, number, number] = [32, 54, 77];

interface Token {
  text: string;
  bold: boolean;
  italic: boolean;
  underline: boolean;
  highlight: boolean;
  isSpace: boolean;
}

export interface RunLine {
  tokens: Array<Token & {width: number}>;
}

const fontStyle = (bold: boolean, italic: boolean) => {
  if (bold && italic) return 'bolditalic';
  if (bold) return 'bold';
  if (italic) return 'italic';
  return 'normal';
};

// Split runs into whitespace-delimited tokens (so we can wrap), plus explicit line breaks.
const tokenize = (runs: StyledRun[]): Array<Token | 'break'> => {
  const tokens: Array<Token | 'break'> = [];
  for (const run of runs) {
    const segments = run.text.split('\n');
    segments.forEach((segment, segmentIndex) => {
      if (segmentIndex > 0) {
        tokens.push('break');
      }
      for (const part of segment.split(/(\s+)/).filter((piece) => piece.length > 0)) {
        tokens.push({
          text: part,
          bold: Boolean(run.bold),
          italic: Boolean(run.italic),
          underline: Boolean(run.underline),
          highlight: Boolean(run.highlight),
          isSpace: /^\s+$/.test(part),
        });
      }
    });
  }
  return tokens;
};

/** Wrap styled runs into visual lines that each fit within maxWidth at the given font size. */
export const wrapRunsToLines = (
  pdf: jsPDF,
  runs: StyledRun[],
  maxWidth: number,
  fontSize: number,
): RunLine[] => {
  pdf.setFontSize(fontSize);
  const lines: RunLine[] = [];
  let current: RunLine = {tokens: []};
  let lineWidth = 0;

  const pushLine = () => {
    lines.push(current);
    current = {tokens: []};
    lineWidth = 0;
  };

  for (const token of tokenize(runs)) {
    if (token === 'break') {
      pushLine();
      continue;
    }
    pdf.setFont('helvetica', fontStyle(token.bold, token.italic));
    const width = pdf.getTextWidth(token.text);

    if (!token.isSpace && current.tokens.length && lineWidth + width > maxWidth) {
      pushLine();
    }
    if (token.isSpace && current.tokens.length === 0) {
      continue; // never start a wrapped line with leading whitespace
    }
    current.tokens.push({...token, width});
    lineWidth += width;
  }
  pushLine();

  return lines.length ? lines : [{tokens: []}];
};

/** Draw a single pre-wrapped line at the given baseline, honoring styling + highlight. */
export const drawRunLine = (pdf: jsPDF, line: RunLine, x: number, baselineY: number, fontSize: number) => {
  let cursorX = x;
  for (const token of line.tokens) {
    pdf.setFont('helvetica', fontStyle(token.bold, token.italic));
    if (token.highlight && !token.isSpace) {
      pdf.setFillColor(HIGHLIGHT_RGB[0], HIGHLIGHT_RGB[1], HIGHLIGHT_RGB[2]);
      pdf.rect(cursorX, baselineY - fontSize * 0.32, token.width, fontSize * 0.42, 'F');
    }
    pdf.setTextColor(TEXT_RGB[0], TEXT_RGB[1], TEXT_RGB[2]);
    pdf.text(token.text, cursorX, baselineY);
    if (token.underline && !token.isSpace) {
      pdf.setDrawColor(TEXT_RGB[0], TEXT_RGB[1], TEXT_RGB[2]);
      pdf.line(cursorX, baselineY + 0.6, cursorX + token.width, baselineY + 0.6);
    }
    cursorX += token.width;
  }
};
