import {describe, expect, it} from 'vitest';

import {
  markMemberNoteLinks,
  normalizePastProjectsDetailHtml,
  pastProjectsDetailHtmlToPlainText,
  plainTextToPastProjectsDetailHtml,
  sanitizePastProjectsDetailHtml,
  stripPastProjectsDetailMarkup,
} from '@/features/projects/components/richText/content/pastProjectsDetailText';
import {
  buildPastProjectsNoteInsertHtml,
} from '@/features/projects/components/richText/content/pastProjectsNoteInsert';
import {countProjectBlocks, makeRow} from '@/__tests__/features/projects/components/richText/content/pastProjectsDetailTextFixtures';

describe('sanitizePastProjectsDetailHtml', () => {
    it.each([
        ['<img src=x onerror=alert(1)><strong>Safe</strong>', '<strong>Safe</strong>'],
        ['<a href="javascript:alert(1)" onclick="alert(2)">click</a>', '<a>click</a>'],
        ['<svg><a xlink:href="javascript:alert(1)">bad</a></svg><mark>keep</mark>', '<mark>keep</mark>'],
        ['<script>alert(1)</script><div style="background:url(javascript:alert(2))">ok</div>', '<div>ok</div>'],
    ])('removes hostile markup while preserving allowed content', (hostile, expected) => {
        const sanitized = sanitizePastProjectsDetailHtml(hostile);

        expect(sanitized).toBe(expected);
        expect(sanitized).not.toMatch(/javascript:|onerror|onclick|<script|<svg/i);
    });

    it('keeps only the curation marker attributes required for reinsertion', () => {
        const sanitized = sanitizePastProjectsDetailHtml(
            '<div data-past-project-note-curation="project-summary" data-past-project-key="safe" data-secret="no">ok</div>',
        );

        expect(sanitized).toBe(
            '<div data-past-project-note-curation="project-summary" data-past-project-key="safe">ok</div>',
        );
    });

    it('converts span background styles into mark highlights', () => {
        expect(sanitizePastProjectsDetailHtml('<span style="background:red">marked</span>')).toBe(
            '<mark>marked</mark>',
        );
    });

    it('converts font bgcolor attributes into mark highlights', () => {
        expect(sanitizePastProjectsDetailHtml('<font bgcolor="red">marked</font>')).toBe('<mark>marked</mark>');
    });
});

describe('markMemberNoteLinks', () => {
    it('marks links to other sites nofollow / ugc / noopener and leaves this site\'s links alone', () => {
        const html = markMemberNoteLinks(
            sanitizePastProjectsDetailHtml(
                '<a href="https://phish.example.net/x" rel="me">a</a><a href="/past-projects/project/1">b</a>' +
                    `<a href="${window.location.origin}/news">c</a><a href="mailto:x@example.com">d</a>`,
            ),
        );

        const template = document.createElement('template');
        template.innerHTML = html;
        expect([...template.content.querySelectorAll('a')].map((link) => link.getAttribute('rel'))).toEqual([
            'nofollow ugc noopener',
            null,
            null,
            'nofollow ugc noopener',
        ]);
    });
});

describe('plainTextToPastProjectsDetailHtml', () => {
    it('escapes html entities and turns newlines into breaks', () => {
        expect(plainTextToPastProjectsDetailHtml('a&b<c>\nnext')).toBe('a&amp;b&lt;c&gt;<br>next');
        expect(plainTextToPastProjectsDetailHtml('line1\r\nline2')).toBe('line1<br>line2');
    });
});

describe('normalizePastProjectsDetailHtml', () => {
    it('sanitizes input that already has markup', () => {
        expect(normalizePastProjectsDetailHtml('<strong onclick="x">bold</strong>')).toBe('<strong>bold</strong>');
    });

    it('escapes plain text that has no markup', () => {
        expect(normalizePastProjectsDetailHtml('a < b')).toBe('a &lt; b');
    });
});

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

    it('turns br tags into newlines', () => {
        expect(pastProjectsDetailHtmlToPlainText('a<br>b')).toBe('a\nb');
    });
});

describe('buildPastProjectsNoteInsertHtml', () => {
    it('wraps each project in a keyed block inside the curation container', () => {
        const html = buildPastProjectsNoteInsertHtml([makeRow(), makeRow({project_title: 'Wind Turbine'})]);
        expect(html).toContain('data-past-project-note-curation="project-summary"');
        expect(countProjectBlocks(html)).toBe(2);
        expect(html).toContain('Solar Cart');
        expect(html).toContain('Wind Turbine');
    });

    it('returns an empty string when every field is excluded', () => {
        const allFields = ['project_label', 'semester_label', 'class_team', 'team_name', 'project_title', 'individual_link', 'organization', 'industry', 'students', 'abstract'] as const;
        const html = buildPastProjectsNoteInsertHtml([makeRow()], {excludedFields: allFields});
        expect(html).toBe('');
    });

    it('emits an individual link only for rows with an id', () => {
        const withId = buildPastProjectsNoteInsertHtml([makeRow({id: 'project-9'})]);
        expect(withId).toContain('Individual Link');
        expect(withId).toContain('/past-projects/project/project-9');

        const withoutId = buildPastProjectsNoteInsertHtml([makeRow({id: ''})]);
        expect(withoutId).not.toContain('Individual Link');
    });

    it("links a current-semester project to its own page, not the archive's", () => {
        const html = buildPastProjectsNoteInsertHtml([makeRow({id: 'current-1', catalog: 'current'})]);

        expect(html).toContain(`href="${window.location.origin}/projects/current-1"`);
        expect(html).not.toContain('/past-projects/project/current-1');
    });

});
