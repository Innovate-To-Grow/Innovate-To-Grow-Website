import {afterEach, describe, expect, it, vi} from 'vitest';

import {
    appendPastProjectsNoteInsertHtml,
    buildPastProjectsNoteInsertHtml,
    copyPastProjectsDetailToClipboard,
    pastProjectsDetailHtmlToPlainText,
    sanitizePastProjectsDetailHtml,
    stripPastProjectsDetailMarkup,
} from '@/features/projects/components/pastProjectsDetailText';
import type {ProjectGridRow} from '@/features/projects/components/projectGrid';

const makeRow = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
    id: '',
    semester_label: '2025-1 Spring',
    class_code: 'ENGR 120',
    team_number: 'T01',
    team_name: 'Team Alpha',
    project_title: 'Solar Cart',
    organization: 'Acme',
    industry: 'Energy',
    abstract: 'An abstract.',
    student_names: 'Alice, Bob',
    is_presenting: '',
    ...overrides,
});

const countProjectBlocks = (html: string) =>
    (html.match(/data-past-project-key=/g) ?? []).length;

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
});

describe('buildPastProjectsNoteInsertHtml', () => {
    it('wraps each project in a keyed block inside the curation container', () => {
        const html = buildPastProjectsNoteInsertHtml([makeRow(), makeRow({project_title: 'Wind Turbine'})]);
        expect(html).toContain('data-past-project-note-curation="project-summary"');
        expect(countProjectBlocks(html)).toBe(2);
        expect(html).toContain('Solar Cart');
        expect(html).toContain('Wind Turbine');
    });

});

describe('appendPastProjectsNoteInsertHtml', () => {
    it('inserts into an empty note', () => {
        const html = appendPastProjectsNoteInsertHtml('', [makeRow()]);
        expect(countProjectBlocks(html)).toBe(1);
        expect(html).toContain('Solar Cart');
    });

    it('preserves note text written outside the inserted block', () => {
        const withNote = appendPastProjectsNoteInsertHtml('<div>My intro note</div>', [makeRow()]);
        expect(withNote).toContain('My intro note');
        expect(countProjectBlocks(withNote)).toBe(1);
    });

    it('re-inserting the same projects adds no duplicates', () => {
        const rows = [makeRow(), makeRow({project_title: 'Wind Turbine'})];
        const first = appendPastProjectsNoteInsertHtml('', rows);
        const second = appendPastProjectsNoteInsertHtml(first, rows);
        expect(countProjectBlocks(second)).toBe(2);
    });

    it('appends only projects not already present and keeps prior edits', () => {
        const first = appendPastProjectsNoteInsertHtml('', [makeRow()]);
        // Simulate a hand edit inside the already-inserted block (rendered text, not the marker attr).
        const edited = first.replace('<strong>Project 1</strong>', '<strong>Project 1</strong><div>HAND-EDITED NOTE</div>');
        const rows = [makeRow(), makeRow({project_title: 'Wind Turbine'})];
        const second = appendPastProjectsNoteInsertHtml(edited, rows);
        expect(countProjectBlocks(second)).toBe(2);
        expect(second).toContain('HAND-EDITED NOTE');
        expect(second).toContain('Wind Turbine');
    });
});

describe('copyPastProjectsDetailToClipboard', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('writes sanitized HTML and matching plain text in one ClipboardItem', async () => {
        const write = vi.fn().mockResolvedValue(undefined);
        const clipboardItems: Array<Record<string, Blob>> = [];

        class MockClipboardItem {
            readonly items: Record<string, Blob>;

            constructor(items: Record<string, Blob>) {
                this.items = items;
                clipboardItems.push(items);
            }
        }

        vi.stubGlobal('ClipboardItem', MockClipboardItem);
        Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {write}});

        await copyPastProjectsDetailToClipboard(
            '<div onclick="alert(1)"><mark>Review</mark></div><script>alert(2)</script>',
        );

        expect(write).toHaveBeenCalledTimes(1);
        expect(clipboardItems).toHaveLength(1);
        expect(await clipboardItems[0]['text/plain'].text()).toBe('Review');
        const clipboardHtml = await clipboardItems[0]['text/html'].text();
        expect(clipboardHtml).toContain('<mark style="background-color:#fff3a3;color:inherit;">Review</mark>');
        expect(clipboardHtml).not.toMatch(/onclick|script|alert/i);
    });

    it('falls back to plain text when rich clipboard writing fails', async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        vi.stubGlobal('ClipboardItem', class MockClipboardItem {
        });
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {write: vi.fn().mockRejectedValue(new Error('not allowed')), writeText},
        });

        await copyPastProjectsDetailToClipboard('<strong>Plain fallback</strong>');

        expect(writeText).toHaveBeenCalledWith('Plain fallback');
    });

});
