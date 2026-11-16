import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  copyPastProjectsDetailToClipboard,
} from '@/features/projects/components/richText/content/pastProjectsDetailText';
import {
  appendPastProjectsNoteInsertHtml,
} from '@/features/projects/components/richText/content/pastProjectsNoteInsert';
import {countProjectBlocks, makeRow} from '@/__tests__/features/projects/components/richText/content/pastProjectsDetailTextFixtures';

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

    it('leaves the note untouched when every field is excluded', () => {
        const allFields = ['project_label', 'semester_label', 'class_team', 'team_name', 'project_title', 'individual_link', 'organization', 'industry', 'students', 'abstract'] as const;
        const existing = '<div>My intro note</div>';
        const html = appendPastProjectsNoteInsertHtml(existing, [makeRow()], {excludedFields: allFields});
        expect(html).toBe(existing);
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

    it('falls back to a hidden textarea and execCommand when no clipboard API exists', async () => {
        vi.stubGlobal('ClipboardItem', undefined);
        Object.defineProperty(navigator, 'clipboard', {configurable: true, value: undefined});
        const execCommand = vi.fn().mockReturnValue(true);
        Object.defineProperty(document, 'execCommand', {configurable: true, value: execCommand, writable: true});
        const appendSpy = vi.spyOn(document.body, 'appendChild');
        const removeSpy = vi.spyOn(HTMLTextAreaElement.prototype, 'remove');

        try {
            await copyPastProjectsDetailToClipboard('<strong>Plain</strong>');

            expect(execCommand).toHaveBeenCalledWith('copy');
            expect(appendSpy).toHaveBeenCalled();
            expect(removeSpy).toHaveBeenCalled();
        } finally {
            Object.defineProperty(document, 'execCommand', {configurable: true, value: undefined, writable: true});
        }
    });

});
