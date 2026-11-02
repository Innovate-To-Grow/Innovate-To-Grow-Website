/**
 * Keep PDF text within the glyphs of the font that draws it. jsPDF has no font fallback: with a built-in font
 * (Windows-1252 only) one missing character turns the whole line into letter-spaced UTF-16 that runs off the page,
 * and with an embedded font the character silently disappears. So a missing character is replaced by the one a
 * reader expects, folded to a covered form, or left out.
 */

/** Tells whether the font has a glyph for a Unicode code point. */
export type GlyphCoverage = (codePoint: number) => boolean;

// Never visible on the site (a soft hyphen shows only where the browser breaks the word), so never drawn.
const INVISIBLE = /[\u00ad\u200b-\u200d\u2060\ufeff]/g;

// Characters that read the same as one the font is more likely to have. Letters with a stroke have no Unicode
// decomposition, so they are spelled the way ASCII transliteration spells them.
const SUBSTITUTES: Record<string, string> = {
  '\u2010': '-', // hyphen
  '\u2011': '-', // non-breaking hyphen
  '\u2012': '\u2013', // figure dash -> en dash
  '\u2015': '\u2014', // horizontal bar -> em dash
  '\u2212': '-', // minus sign
  '\u0141': 'L',
  '\u0142': 'l',
  '\u0110': 'D',
  '\u0111': 'd',
  '\u0126': 'H',
  '\u0127': 'h',
  '\u0131': 'i', // dotless i
  '\u0166': 'T',
  '\u0167': 't',
};

const COMBINING_MARK = /\p{M}/u;

const codePointOf = (char: string) => char.codePointAt(0) ?? 0;

const fallbackFor = (char: string, hasGlyph: GlyphCoverage) => {
  const substitute = SUBSTITUTES[char];
  if (substitute && [...substitute].every((part) => hasGlyph(codePointOf(part)))) {
    return substitute;
  }
  if (/\s/u.test(char)) {
    return ' ';
  }
  // Compatibility decomposition keeps what the font can draw: 𝝅 → π, ﬁ → fi, ć → c (the accent is dropped).
  return [...char.normalize('NFKD')]
    .filter((part) => !COMBINING_MARK.test(part) && hasGlyph(codePointOf(part)))
    .join('');
};

/** The text with every character the font cannot draw replaced, folded or removed. Line breaks are kept. */
export const createGlyphFallback = (hasGlyph: GlyphCoverage) => (text: string) => {
  let drawable = '';
  // NFC first, so a letter typed as base + combining accent is drawn as the font's precomposed glyph.
  for (const char of text.replace(/\r\n?/g, '\n').replace(INVISIBLE, '').normalize('NFC')) {
    drawable += char === '\n' || hasGlyph(codePointOf(char)) ? char : fallbackFor(char, hasGlyph);
  }
  return drawable;
};

// Windows-1252 code points above Latin-1: the only non-Latin-1 characters jsPDF's built-in fonts can encode.
const WIN_ANSI_EXTRAS = new Set([
  0x0152, 0x0153, 0x0160, 0x0161, 0x0178, 0x017d, 0x017e, 0x0192, 0x02c6, 0x02dc, 0x2013, 0x2014, 0x2018, 0x2019,
  0x201a, 0x201c, 0x201d, 0x201e, 0x2020, 0x2021, 0x2022, 0x2026, 0x2030, 0x2039, 0x203a, 0x20ac, 0x2122,
]);

/** Coverage of jsPDF's built-in Helvetica (WinAnsiEncoding). */
export const hasWinAnsiGlyph: GlyphCoverage = (codePoint) =>
  (codePoint >= 0x20 && codePoint <= 0x7e) ||
  (codePoint >= 0xa0 && codePoint <= 0xff) ||
  WIN_ANSI_EXTRAS.has(codePoint);
