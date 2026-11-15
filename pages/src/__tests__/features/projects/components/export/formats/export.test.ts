import {afterEach, describe, expect, it, vi} from 'vitest';
import {createProjectRowsWordBlob} from '@/features/projects/components/export/formats/wordExport';
import {loadI2gLogoAsset} from '@/features/projects/components/export/support/logoAsset';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {triggerDownload} from '@/features/projects/components/export/support/exportTypes';

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

describe('createProjectRowsWordBlob', () => {
    it('creates a real docx package with the project columns and branding', async () => {
        const blob = createProjectRowsWordBlob(
            [row],
            {title: 'Shared Results', note: 'Owner note & review instructions'},
            logo,
        );

        expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document');

        const bytes = new Uint8Array(await blob.arrayBuffer());
        expect(String.fromCharCode(...bytes.slice(0, 2))).toBe('PK');

        const packageText = new TextDecoder().decode(bytes);
        expect(packageText).toContain('[Content_Types].xml');
        expect(packageText).toContain('word/document.xml');
        expect(packageText).toContain('word/media/i2g-logo.png');
        expect(packageText).toContain('Shared Results');
        expect(packageText).toContain('Owner note &amp; review instructions');
        expect(packageText).toContain('Rotary Joint Testing System');
        expect(packageText).toContain('Student Names');
        expect(packageText).toContain('A detailed abstract with &lt;special&gt; characters &amp; project context.');
        // The per-project Notes column was removed.
        expect(packageText).not.toContain('Notes');
    });

    it('omits the logo parts from the Word package when no logo is provided', async () => {
        const blob = createProjectRowsWordBlob([row], {title: 'No Logo Export'});
        const packageText = new TextDecoder().decode(new Uint8Array(await blob.arrayBuffer()));

        expect(packageText).not.toContain('rIdLogo');
        expect(packageText).not.toContain('word/media/i2g-logo.png');
        expect(packageText).toContain('No Logo Export');
        expect(packageText).toContain('Rotary Joint Testing System');
    });

    it('heads the document as Past Projects, or with the heading the context gives', async () => {
        const packageText = async (blob: Blob) => new TextDecoder().decode(new Uint8Array(await blob.arrayBuffer()));

        expect(await packageText(createProjectRowsWordBlob([row], {title: 'Archive picks'}))).toContain(
            'Innovate to Grow Past Projects',
        );
        const mixed = await packageText(
            createProjectRowsWordBlob([row], {title: 'Mixed picks', heading: 'Innovate to Grow Projects'}),
        );
        expect(mixed).toContain('Innovate to Grow Projects');
        expect(mixed).not.toContain('Innovate to Grow Past Projects');
    });
});

describe('loadI2gLogoAsset', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('returns null when the logo fetch is not ok', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: false}));
        expect(await loadI2gLogoAsset()).toBeNull();
    });

    it('returns null when the logo fetch throws', async () => {
        vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
        expect(await loadI2gLogoAsset()).toBeNull();
    });

    it('decodes the logo into base64 + bytes on success', async () => {
        const bytes = new Uint8Array([137, 80, 78, 71]);
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: true, arrayBuffer: async () => bytes.buffer}));

        const asset = await loadI2gLogoAsset();

        expect(asset).not.toBeNull();
        expect(asset?.extension).toBe('png');
        expect(asset?.bytes).toHaveLength(4);
        expect(asset?.dataUrl.startsWith('data:image/png;base64,')).toBe(true);
    });
});

describe('triggerDownload', () => {
    it('clicks a temporary download link and always revokes its object URL', () => {
        const blob = new Blob(['download body'], {type: 'text/plain'});
        const createObjectURL = vi.fn().mockReturnValue('blob:download-123');
        const revokeObjectURL = vi.fn();
        const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
        vi.stubGlobal('URL', {...URL, createObjectURL, revokeObjectURL});

        triggerDownload(blob, 'past-projects.txt');

        expect(createObjectURL).toHaveBeenCalledWith(blob);
        expect(click).toHaveBeenCalledTimes(1);
        const link = click.mock.instances[0] as HTMLAnchorElement;
        expect(link.href).toBe('blob:download-123');
        expect(link.download).toBe('past-projects.txt');
        expect(link.isConnected).toBe(false);
        expect(revokeObjectURL).toHaveBeenCalledWith('blob:download-123');

        click.mockRestore();
        vi.unstubAllGlobals();
    });

});
