import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/merged/composition/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

// The export functions are heavy (dynamic imports of exceljs/jspdf + downloads) and are covered
// directly in the export module tests; here we stub them so we can assert the component's wiring
// and error handling without triggering real downloads.
const exportMocks = vi.hoisted(() => ({
  exportProjectRowsExcel: vi.fn(),
  exportProjectRowsPdf: vi.fn(),
  exportProjectRowsWord: vi.fn(),
}));

vi.mock('@/features/projects/components/export/formats/excelExport', () => ({
  exportProjectRowsExcel: exportMocks.exportProjectRowsExcel,
}));
vi.mock('@/features/projects/components/export/formats/pdfExport', () => ({
  exportProjectRowsPdf: exportMocks.exportProjectRowsPdf,
}));
vi.mock('@/features/projects/components/export/formats/wordExport', () => ({
  exportProjectRowsWord: exportMocks.exportProjectRowsWord,
}));

const baseRow: ProjectGridRow = {
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: 'T01',
  team_name: 'Team Alpha',
  project_title: 'Shared Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: 'A detailed project abstract.',
  student_names: 'Alice, Bob',
  is_presenting: '',
};

const addedRow: ProjectGridRow = {
  ...baseRow,
  team_number: 'T02',
  team_name: 'Team Beta',
  project_title: 'Irrigation Sensor',
  organization: 'Blue Diamond',
};

const rowWithId: ProjectGridRow = {
  ...baseRow,
  id: '11111111-1111-4111-8111-111111111111',
};

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

const setRichTextEditorHtml = (editor: HTMLElement, html: string) => {
  editor.innerHTML = html;
  fireEvent.input(editor);
};

describe('MergedResultsTable', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
    exportMocks.exportProjectRowsExcel.mockReset().mockResolvedValue(undefined);
    exportMocks.exportProjectRowsPdf.mockReset().mockResolvedValue(undefined);
    exportMocks.exportProjectRowsWord.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('inserts visible project details and individual links into the share note', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');

    render(<MergedResultsTable rows={makeItems([rowWithId])} onCreateShare={onCreateShare} />);

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    fireEvent.click(screen.getByRole('button', {name: 'Insert Projects into Note'}));

    const expectedIndividualHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
    expect(noteEditor.textContent).toContain('Project Title: Shared Project');
    expect(noteEditor.textContent).toContain(`Individual Link: ${expectedIndividualHref}`);
    const insertedLink = noteEditor.querySelector('a');
    expect(insertedLink?.getAttribute('href')).toBe(expectedIndividualHref);

    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'Spring finalists'}});
    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    const noteArg = onCreateShare.mock.calls[0][2];
    expect(noteArg).toContain('Project Title');
    expect(noteArg).toContain(`<a href="${expectedIndividualHref}">`);
  });

  it('inserts curation content when the note editor was focused', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId])} onCreateShare={vi.fn()} />);

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    const insertButton = screen.getByRole('button', {name: 'Insert Projects into Note'});
    noteEditor.focus();
    expect(noteEditor).toHaveFocus();

    insertButton.focus();
    fireEvent.click(insertButton);

    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
    expect(noteEditor.textContent).toContain('Project Title: Shared Project');
  });

  it('excludes configured project fields from inserted note text', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId])} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: 'Choose Fields'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Individual Link'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Abstract'}));
    fireEvent.click(screen.getByRole('button', {name: 'Insert Projects into Note'}));

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
    expect(noteEditor.textContent).toContain('Project Title: Shared Project');
    expect(noteEditor.textContent).not.toContain('Individual Link');
    expect(noteEditor.textContent).not.toContain('Abstract');
    expect(noteEditor.querySelector('a')).toBeNull();
  });

  it('updates the existing curated note block without overwriting manual note text', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId, addedRow])} onCreateShare={vi.fn()} />);

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    setRichTextEditorHtml(noteEditor, '<div>Manual intro</div>');
    fireEvent.click(screen.getByRole('button', {name: 'Insert Projects into Note'}));

    await waitFor(() => expect(noteEditor.textContent).toContain('Project 2'));
    expect(noteEditor.textContent).toContain('Manual intro');
    expect(noteEditor.querySelectorAll('[data-past-project-note-curation="project-summary"]')).toHaveLength(1);

    // Re-inserting keeps the manual intro and the existing curated block intact: projects already in
    // the block are not rebuilt or duplicated (they survive hand edits), so a single curation
    // container holds exactly one "Project 1" entry.
    fireEvent.click(screen.getByRole('button', {name: 'Insert Projects into Note'}));

    await waitFor(() => expect(noteEditor.textContent).toContain('Project 2'));
    expect(noteEditor.textContent).toContain('Manual intro');
    expect(noteEditor.textContent?.match(/Project 1/g)).toHaveLength(1);
    expect(noteEditor.querySelectorAll('[data-past-project-note-curation="project-summary"]')).toHaveLength(1);
  });

  it('re-includes an excluded field when the checkbox is toggled again', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId])} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: 'Choose Fields'}));
    const individualLinkCheckbox = screen.getByRole('checkbox', {name: 'Individual Link'});
    fireEvent.click(individualLinkCheckbox);
    fireEvent.click(individualLinkCheckbox);
    fireEvent.click(screen.getByRole('button', {name: 'Insert Projects into Note'}));

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    await waitFor(() => expect(noteEditor.textContent).toContain('Individual Link'));
  });
});
