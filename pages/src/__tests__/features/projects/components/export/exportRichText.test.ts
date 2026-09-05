import {describe, expect, it} from 'vitest';

import {parseRichTextRuns, runsToPlainText} from '@/features/projects/components/export/exportRichText';

describe('parseRichTextRuns', () => {
  it('returns [] for empty input', () => {
    expect(parseRichTextRuns('')).toEqual([]);
    expect(parseRichTextRuns('   ')).toEqual([]);
    expect(parseRichTextRuns(undefined as unknown as string)).toEqual([]);
  });

  it('parses plain text into a single run', () => {
    expect(parseRichTextRuns('hello world')).toEqual([{text: 'hello world'}]);
  });

  it('maps b/strong to bold', () => {
    expect(parseRichTextRuns('<b>bold</b>')).toEqual([{text: 'bold', bold: true}]);
    expect(parseRichTextRuns('<strong>bold</strong>')).toEqual([{text: 'bold', bold: true}]);
  });

  it('maps i/em to italic, u to underline, and mark to highlight', () => {
    expect(parseRichTextRuns('<i>x</i>')).toEqual([{text: 'x', italic: true}]);
    expect(parseRichTextRuns('<em>x</em>')).toEqual([{text: 'x', italic: true}]);
    expect(parseRichTextRuns('<u>x</u>')).toEqual([{text: 'x', underline: true}]);
    expect(parseRichTextRuns('<mark>x</mark>')).toEqual([{text: 'x', highlight: true}]);
  });

  it('merges consecutive runs that share styling', () => {
    expect(parseRichTextRuns('<b>a</b><b>b</b>')).toEqual([{text: 'ab', bold: true}]);
  });

  it('normalizes &nbsp; back to a regular space', () => {
    expect(parseRichTextRuns('a&nbsp;b')).toEqual([{text: 'a b'}]);
  });

  it('turns block tags into line breaks', () => {
    const runs = parseRichTextRuns('<div>line1</div><div>line2</div>');
    expect(runsToPlainText(runs)).toBe('line1\nline2');
  });

  it('turns <br> into a line break', () => {
    const runs = parseRichTextRuns('a<br>b');
    expect(runsToPlainText(runs)).toBe('a\nb');
  });
});

describe('runsToPlainText', () => {
  it('joins run texts', () => {
    expect(runsToPlainText([{text: 'a'}, {text: 'b'}])).toBe('ab');
  });

  it('returns empty for no runs', () => {
    expect(runsToPlainText([])).toBe('');
  });
});
