import {describe, expect, it, vi} from 'vitest';

import {drawRunLine, wrapRunsToLines} from '@/features/projects/components/export/pdfRichText';

type Pdf = Parameters<typeof wrapRunsToLines>[0];

function fakePdf() {
  return {
    setFontSize: vi.fn(),
    setFont: vi.fn(),
    getTextWidth: (text: string) => text.length,
    setFillColor: vi.fn(),
    rect: vi.fn(),
    setTextColor: vi.fn(),
    text: vi.fn(),
    setDrawColor: vi.fn(),
    line: vi.fn(),
  };
}

describe('wrapRunsToLines', () => {
  it('wraps tokens that exceed maxWidth onto a new line', () => {
    const pdf = fakePdf() as unknown as Pdf;
    const lines = wrapRunsToLines(pdf, [{text: 'a b c'}], 3, 10);

    expect(lines).toHaveLength(2);
    expect(lines[0].tokens.map((token) => token.text).join('')).toBe('a b ');
    expect(lines[1].tokens.map((token) => token.text).join('')).toBe('c');
  });

  it('never starts a wrapped line with leading whitespace', () => {
    const pdf = fakePdf() as unknown as Pdf;
    const lines = wrapRunsToLines(pdf, [{text: '  x'}], 100, 10);

    expect(lines).toHaveLength(1);
    expect(lines[0].tokens.map((token) => token.text).join('')).toBe('x');
  });

  it('treats explicit newlines as line breaks', () => {
    const pdf = fakePdf() as unknown as Pdf;
    const lines = wrapRunsToLines(pdf, [{text: 'a\nb'}], 100, 10);

    expect(lines.map((line) => line.tokens.map((token) => token.text).join(''))).toEqual(['a', 'b']);
  });

  it('returns a single empty line for empty runs', () => {
    const pdf = fakePdf() as unknown as Pdf;
    expect(wrapRunsToLines(pdf, [], 100, 10)).toEqual([{tokens: []}]);
  });
});

describe('drawRunLine', () => {
  it('draws each token with its font style and text color', () => {
    const pdf = fakePdf() as unknown as Pdf;
    const line = {
      tokens: [{text: 'hi', bold: true, italic: false, underline: false, highlight: false, isSpace: false, width: 2}],
    };

    drawRunLine(pdf, line, 0, 10, 9);

    expect(pdf.setFont).toHaveBeenCalledWith('helvetica', 'bold');
    expect(pdf.setTextColor).toHaveBeenCalled();
    expect(pdf.text).toHaveBeenCalledWith('hi', 0, 10);
  });

  it('draws a highlight rect and underline for marked/underlined tokens', () => {
    const pdf = fakePdf() as unknown as Pdf;
    const line = {
      tokens: [{text: 'x', bold: false, italic: false, underline: true, highlight: true, isSpace: false, width: 1}],
    };

    drawRunLine(pdf, line, 5, 10, 9);

    expect(pdf.setFillColor).toHaveBeenCalled();
    expect(pdf.rect).toHaveBeenCalled();
    expect(pdf.setDrawColor).toHaveBeenCalled();
    expect(pdf.line).toHaveBeenCalled();
  });

  it('skips highlight and underline for whitespace tokens', () => {
    const pdf = fakePdf() as unknown as Pdf;
    const line = {
      tokens: [{text: ' ', bold: false, italic: false, underline: true, highlight: true, isSpace: true, width: 1}],
    };

    drawRunLine(pdf, line, 0, 10, 9);

    expect(pdf.rect).not.toHaveBeenCalled();
    expect(pdf.line).not.toHaveBeenCalled();
  });
});
