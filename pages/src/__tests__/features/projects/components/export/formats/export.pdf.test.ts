import {afterEach, describe, expect, it, vi} from 'vitest';
import {exportProjectRowsPdf} from '@/features/projects/components/export/formats/pdfExport';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
// jspdf is heavy and DOM/canvas-bound; mock it so we can assert the document assembly wiring
// (sections + per-project field lines drawn) without rendering a real PDF.
const pdfTextCalls = vi.hoisted(() => [] as string[]);

vi.mock('jspdf', () => {
    class MockJsPdf {
        internal = {pageSize: {getWidth: () => 297, getHeight: () => 210}};
        setTextColor = vi.fn();
        setFont = vi.fn();
        setFontSize = vi.fn();
        setDrawColor = vi.fn();
        setLineWidth = vi.fn();
        setFillColor = vi.fn();
        line = vi.fn();
        rect = vi.fn();
        addPage = vi.fn();
        addImage = vi.fn();
        save = vi.fn();

        getTextWidth(text: string) {
            return text.length;
        }

        splitTextToSize(text: string) {
            return [text];
        }

        text(value: string | string[]) {
            pdfTextCalls.push(...(Array.isArray(value) ? value : [value]));
        }
    }

    return {jsPDF: MockJsPdf};
});

const row: ProjectGridRow = {
    semester_label: '2025 Spring',
    class_code: 'CAP',
    team_number: '101',
    team_name: 'General Rotary and Professional Engineering',
    project_title: 'Rotary Joint Testing System',
    organization: 'E&J Gallo Winery',
    industry: 'Food Processing',
    abstract: 'A detailed abstract with <special> characters & project context.',
    student_names: 'Alice Calderon, Bob Lee',
    is_presenting: '',
};

describe('exportProjectRowsPdf', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
        pdfTextCalls.length = 0;
    });

    it('draws the header, sections, and a per-project block with project fields', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: false})); // logo load fails -> null

        await exportProjectRowsPdf([row], 'past-projects', {title: 'PDF Title', note: 'Owner note'});

        const drawnText = pdfTextCalls.join('|');
        expect(drawnText).toContain('PDF Title');
        expect(drawnText).toContain('Innovate to Grow Past Projects');
        expect(drawnText).toContain('Note');
        expect(drawnText).toContain('Projects');
        // Per-project block: title bar + field labels.
        expect(drawnText).toContain('Project 1: Rotary Joint Testing System');
        expect(drawnText).toContain('Year-Semester: ');
        expect(drawnText).toContain('Abstract: ');
        // The per-project Notes field was removed.
        expect(pdfTextCalls).not.toContain('Notes: ');
    });

    it('draws the heading the context gives under the title', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: false}));

        await exportProjectRowsPdf([row], 'projects', {title: 'Mixed picks', heading: 'Innovate to Grow Projects'});

        expect(pdfTextCalls).toContain('Innovate to Grow Projects');
        expect(pdfTextCalls).not.toContain('Innovate to Grow Past Projects');
    });
});
