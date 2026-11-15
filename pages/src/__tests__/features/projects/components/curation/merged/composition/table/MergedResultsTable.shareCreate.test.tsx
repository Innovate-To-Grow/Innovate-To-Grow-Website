import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/curation/merged/composition/MergedResultsTable';
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

  it('submits the name and note inside the rows when creating a share', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');

    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'Spring finalists'}});
    setRichTextEditorHtml(
      screen.getByRole('textbox', {name: /curation note/i}),
      'Review these with the team',
    );
    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    expect(onCreateShare).toHaveBeenCalledTimes(1);
    const [rowsArg, nameArg, noteArg] = onCreateShare.mock.calls[0];
    expect(onCreateShare.mock.calls[0]).toHaveLength(3); // no detailsText 4th arg
    expect(nameArg).toBe('Spring finalists');
    expect(noteArg).toBe('Review these with the team');
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(await screen.findByText('Saved. Opening your curation…')).toBeInTheDocument();
  });

  it('shares only the rows matching the active search filter in builder mode', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} onCreateShare={onCreateShare} />);

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'Irrigation'}});
    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'Filtered'}});
    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    const rowsArg = onCreateShare.mock.calls[0][0];
    expect(rowsArg).toHaveLength(1);
    expect(rowsArg[0]).toMatchObject({project_title: 'Irrigation Sensor'});
  });

  it('hides the share controls and offers Sign In to Save where the save buttons would be', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});
    render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);

    expect(screen.queryByRole('button', {name: /save curation/i})).toBeNull();
    expect(screen.queryByLabelText(/curation name/i)).toBeNull();
    // The card header's button again under "Save this curation", as for a member, and no sign-in sentence.
    const signInLinks = screen.getAllByRole('link', {name: 'Sign In to Save'});
    expect(signInLinks).toHaveLength(2);
    for (const link of signInLinks) {
      expect(link).toHaveClass('itg-btn', 'itg-btn-primary');
      // Each carries a returnTo, so sign-in brings the visitor back to this page.
      expect(link.getAttribute('href')).toMatch(/^\/login\?returnTo=/);
    }
    expect(screen.queryByText(/Sign in to save this curation/i)).toBeNull();
    const section = screen.getByRole('heading', {name: 'Save this curation'}).closest('.project-grid-share') as HTMLElement;
    expect(within(section).getByText('Saved curations are listed under My Curations, each with a link anyone can view.'))
      .toBeInTheDocument();
  });

  it('blocks creating a share with more than 1000 projects', async () => {
    const onCreateShare = vi.fn();
    const manyRows = Array.from({length: 1001}, (_, index) => ({
      ...baseRow,
      team_number: `T${index}`,
      project_title: `Project ${index}`,
    }));

    render(<MergedResultsTable rows={createProjectGridItems(manyRows, 'test')} onCreateShare={onCreateShare} />);

    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    expect(await screen.findByText(/at most 1000 projects/i)).toBeInTheDocument();
    expect(onCreateShare).not.toHaveBeenCalled();
  });

  it('surfaces a specific DRF validation message when share creation fails', async () => {
    const onCreateShare = vi.fn().mockRejectedValue({
      response: {data: {name: ['Name is too long.']}},
    });

    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    expect(await screen.findByText('Name is too long.')).toBeInTheDocument();
  });
});
