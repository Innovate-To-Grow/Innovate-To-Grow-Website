import {describe, expect, it} from 'vitest';

import {createGlyphFallback, hasWinAnsiGlyph} from '@/features/projects/components/export/support/glyphFallback';

const NON_BREAKING_HYPHEN = '\u2011';
const NARROW_NO_BREAK_SPACE = '\u202f';
const SOFT_HYPHEN = '\u00ad';
const ZERO_WIDTH_JOINER = '\u200d';
const COMBINING_DOUBLE_MACRON_BELOW = '\u035f';
const COMBINING_ACUTE = '\u0301';
const MATH_SANS_BOLD_ITALIC_PI = '\u{1d745}';
const MANGO = '\u{1f96d}';

// Windows-1252 plus Latin Extended, Greek and Vietnamese but no combining marks: roughly what Open Sans covers.
const LATIN_GREEK = (codePoint: number) =>
  hasWinAnsiGlyph(codePoint) ||
  (codePoint >= 0x0100 && codePoint <= 0x02ff) ||
  (codePoint >= 0x0370 && codePoint <= 0x03ff) ||
  (codePoint >= 0x1e00 && codePoint <= 0x1eff);

describe('createGlyphFallback', () => {
  const toWinAnsi = createGlyphFallback(hasWinAnsiGlyph);
  const toLatinGreek = createGlyphFallback(LATIN_GREEK);

  it('keeps text the font covers, including line breaks', () => {
    expect(toLatinGreek('Ana \u017divanovi\u0107, Nguy\u1ec5n V\u0103n An, \u03c9SST')).toBe(
      'Ana \u017divanovi\u0107, Nguy\u1ec5n V\u0103n An, \u03c9SST',
    );
    expect(toWinAnsi('first\r\nsecond\rthird')).toBe('first\nsecond\nthird');
  });

  it('prints a non-breaking hyphen as a hyphen instead of dropping it', () => {
    expect(toWinAnsi(`real${NON_BREAKING_HYPHEN}time Farm${NON_BREAKING_HYPHEN}NG`)).toBe('real-time Farm-NG');
    expect(toLatinGreek(`open${NON_BREAKING_HYPHEN}source`)).toBe('open-source');
  });

  it('turns uncovered spaces and tabs into plain spaces', () => {
    expect(toWinAnsi(`10${NARROW_NO_BREAK_SPACE}kg\tteam`)).toBe('10 kg team');
  });

  it('never draws characters the site does not show, even when the font has them', () => {
    expect(toWinAnsi(`infor${SOFT_HYPHEN}mation`)).toBe('information');
  });

  it('folds letters the font lacks to the form it has, and drops their accents', () => {
    expect(toWinAnsi('Ana \u017divanovi\u0107')).toBe('Ana \u017divanovic');
    expect(toWinAnsi('Nguy\u1ec5n V\u0103n An, \u0141ukasz')).toBe('Nguyen Van An, Lukasz');
    expect(toLatinGreek(`${MATH_SANS_BOLD_ITALIC_PI}-Hard`)).toBe('\u03c0-Hard');
  });

  it('composes a base letter and a combining accent into the precomposed letter', () => {
    expect(toWinAnsi(`Jose${COMBINING_ACUTE}`)).toBe('Jos\u00e9');
  });

  it('leaves out what has no drawable form: emoji, joiners, lone combining marks, other scripts', () => {
    expect(toLatinGreek(`${MANGO}MangoDB${MANGO}`)).toBe('MangoDB');
    expect(toLatinGreek(`\u{1f468}${ZERO_WIDTH_JOINER}\u{1f4bb} Coders`)).toBe(' Coders');
    expect(toLatinGreek(`T${COMBINING_DOUBLE_MACRON_BELOW}H\u0113 L\u014dk\u0101t\u0259rs`)).toBe(
      'TH\u0113 L\u014dk\u0101t\u0259rs',
    );
    expect(toWinAnsi('\u03c9SST')).toBe('SST');
  });

  it('keeps a substitute only when the font can draw it', () => {
    const asciiLettersOnly = createGlyphFallback((codePoint) => /[A-Za-z]/.test(String.fromCodePoint(codePoint)));
    expect(asciiLettersOnly(`a${NON_BREAKING_HYPHEN}b`)).toBe('ab');
  });
});

describe('hasWinAnsiGlyph', () => {
  it('covers printable ASCII, Latin-1 and the Windows-1252 extras only', () => {
    const covered = (char: string) => hasWinAnsiGlyph(char.codePointAt(0) ?? 0);
    expect(['A', '~', '\u00e9', '\u00ff', '\u20ac', '\u2014', '\u017d'].every(covered)).toBe(true);
    expect(['\t', '\u007f', '\u0107', '\u2011', '\u03c9'].some(covered)).toBe(false);
  });
});
