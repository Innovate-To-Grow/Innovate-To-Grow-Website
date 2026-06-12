import {describe, expect, it} from 'vitest';

import {
  pastProjectsDetailHtmlToPlainText,
  stripPastProjectsDetailMarkup,
} from '../pastProjectsDetailText';

describe('stripPastProjectsDetailMarkup', () => {
  it('converts breaks and block closers to newlines', () => {
    expect(stripPastProjectsDetailMarkup('a<br>b')).toBe('a\nb');
    expect(stripPastProjectsDetailMarkup('<div>hello</div><p>world</p>')).toBe('hello\nworld\n');
  });

  it('strips emphasis tags while keeping their text', () => {
    expect(stripPastProjectsDetailMarkup('<strong>bold</strong> and <mark>marked</mark>')).toBe('bold and marked');
  });

  it('leaves no residual markup when fragments could re-form tags', () => {
    // Regression for the single-pass sanitization flaw (CodeQL
    // js/incomplete-multi-character-sanitization): nested/split fragments must
    // not survive as working tags after stripping.
    const hostile = [
      '<<br>script>alert(1)<</p>/script>',
      '<scr<div>ipt>alert(1)</scr</div>ipt>',
      '<<div><br></div>b>payload</b>',
      '<a<b>>x<</i>/a>',
    ];
    for (const input of hostile) {
      const output = stripPastProjectsDetailMarkup(input);
      expect(output).not.toMatch(/<[^>]*>/);
    }
  });

});

describe('pastProjectsDetailHtmlToPlainText', () => {
  it('flattens sanitized rich text to plain text', () => {
    expect(pastProjectsDetailHtmlToPlainText('<div><strong>Team:</strong> Alpha</div><div>Beta</div>')).toBe(
      'Team: Alpha\nBeta',
    );
  });

  it('drops script content entirely via sanitization', () => {
    const text = pastProjectsDetailHtmlToPlainText('<div>ok</div><script>alert(1)</script>');
    expect(text).toBe('ok');
    expect(text).not.toContain('<');
  });
});
