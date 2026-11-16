import ExcelJS from 'exceljs';
import {describe, expect, it, vi} from 'vitest';

import {buildProjectsWorksheet} from '@/features/projects/components/export/formats/excelExport';
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

const logo = {
    base64: 'iVBORw0KGgo=',
    bytes: Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]),
    dataUrl: 'data:image/png;base64,iVBORw0KGgo=',
    extension: 'png' as const,
};

describe('buildProjectsWorksheet', () => {
    it('builds a branded worksheet with the project rows and embedded logo', () => {
        const workbook = new ExcelJS.Workbook();
        buildProjectsWorksheet(workbook, [row], {title: 'Excel Title', note: 'Owner note'}, logo);

        const worksheet = workbook.getWorksheet('Projects');
        expect(worksheet).toBeDefined();
        expect(worksheet?.getCell(1, 2).value).toBe('Excel Title');
        expect(worksheet?.getCell(2, 2).value).toBe('Innovate to Grow Past Projects');
        expect(worksheet?.getImages()).toHaveLength(1);
        // 9 columns (the Notes column was removed).
        expect(worksheet?.columns).toHaveLength(9);

        const cellText: string[] = [];
        worksheet?.eachRow((sheetRow) =>
            sheetRow.eachCell((cell) => {
                const value = cell.value as { richText?: Array<{ text: string }> } | string | null;
                if (value && typeof value === 'object' && 'richText' in value && value.richText) {
                    cellText.push(value.richText.map((part) => part.text).join(''));
                } else {
                    cellText.push(String(value ?? ''));
                }
            }),
        );
        const joined = cellText.join('|');
        expect(joined).toContain('Note'); // the Note section row
        expect(joined).toContain('Projects');
        expect(joined).toContain('Student Names');
        expect(joined).toContain('Rotary Joint Testing System');
        expect(joined).not.toContain('Notes');
    });

    it('serializes the generated workbook to XLSX and reloads it', async () => {
        const workbook = new ExcelJS.Workbook();
        buildProjectsWorksheet(workbook, [row], {title: 'Round-trip Excel'}, null);

        const buffer = await workbook.xlsx.writeBuffer();
        const bytes = new Uint8Array(buffer);

        expect(bytes[0]).toBe(0x50);
        expect(bytes[1]).toBe(0x4b);

        const reloadedWorkbook = new ExcelJS.Workbook();
        await reloadedWorkbook.xlsx.load(buffer);
        const worksheet = reloadedWorkbook.getWorksheet('Projects');
        const cellText: string[] = [];

        worksheet?.eachRow((sheetRow) =>
            sheetRow.eachCell((cell) => {
                cellText.push(cell.text);
            }),
        );

        expect(worksheet).toBeDefined();
        expect(cellText).toContain('Round-trip Excel');
        expect(cellText).toContain('Rotary Joint Testing System');
    });

    it('builds the worksheet without an image when no logo is provided', () => {
        const workbook = new ExcelJS.Workbook();
        buildProjectsWorksheet(workbook, [row], {title: 'No Logo'}, null);
        expect(workbook.getWorksheet('Projects')?.getImages()).toHaveLength(0);
    });

    it('names the list with the heading the context gives', () => {
        const workbook = new ExcelJS.Workbook();
        buildProjectsWorksheet(workbook, [row], {title: 'Mixed picks', heading: 'Innovate to Grow Projects'}, null);
        expect(workbook.getWorksheet('Projects')?.getCell(2, 2).value).toBe('Innovate to Grow Projects');
    });
});
