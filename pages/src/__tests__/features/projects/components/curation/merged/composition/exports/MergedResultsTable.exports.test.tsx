
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

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

const getExportButtonLabels = (container: HTMLElement) => {
  const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]');
  expect(exportCluster).not.toBeNull();
  return within(exportCluster as HTMLElement).getAllByRole('button').map((button) => button.textContent);
};

const setRichTextEditorHtml = (editor: HTMLElement, html: string) => {
  editor.innerHTML = html;
  fireEvent.input(editor);
};

describe('MergedResultsTable exports and row details', () => {
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

  it('offers only Excel, PDF, and Word exports (no CSV)', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    expect(getExportButtonLabels(container)).toEqual(['PDF', 'Excel', 'Word']);
  });

  it('passes the visible rows and export context to the chosen exporter', async () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector(
      '.project-grid-toolbar-cluster[aria-label="Export"]',
    ) as HTMLElement;

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Excel'}));

    await waitFor(() => expect(exportMocks.exportProjectRowsExcel).toHaveBeenCalledTimes(1));
    const [rowsArg, fileBaseName, context] = exportMocks.exportProjectRowsExcel.mock.calls[0];
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(fileBaseName).toBe('past-projects');
    expect(context).toMatchObject({title: 'Curation Draft'});
  });

  it('exports with the typed name and note so the PDF matches the page it will share', async () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'CSE capstones for Bob'}});
    setRichTextEditorHtml(screen.getByRole('textbox', {name: /curation note/i}), 'Hello Bob');
    const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]') as HTMLElement;
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'PDF'}));

    await waitFor(() => expect(exportMocks.exportProjectRowsPdf).toHaveBeenCalledTimes(1));
    const [, fileBaseName, context] = exportMocks.exportProjectRowsPdf.mock.calls[0];
    expect(fileBaseName).toBe('past-projects-cse-capstones-for-bob');
    expect(context).toEqual({title: 'CSE capstones for Bob', note: 'Hello Bob'});
  });

  it('surfaces an error message when an export fails', async () => {
    exportMocks.exportProjectRowsExcel.mockRejectedValueOnce(new Error('chunk load failed'));
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector(
      '.project-grid-toolbar-cluster[aria-label="Export"]',
    ) as HTMLElement;

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Excel'}));

    expect(await screen.findByText('Unable to export Excel. Please try again.')).toBeInTheDocument();
  });

  it('disables every export button when there are no rows to export', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([])} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector(
      '.project-grid-toolbar-cluster[aria-label="Export"]',
    ) as HTMLElement;

    within(exportCluster)
      .getAllByRole('button')
      .forEach((exportButton) => expect(exportButton).toBeDisabled());
  });

  it('exports PDF through the pdf exporter with the export context', async () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector(
      '.project-grid-toolbar-cluster[aria-label="Export"]',
    ) as HTMLElement;

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'PDF'}));

    await waitFor(() => expect(exportMocks.exportProjectRowsPdf).toHaveBeenCalledTimes(1));
    const [rowsArg, fileBaseName, context] = exportMocks.exportProjectRowsPdf.mock.calls[0];
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(fileBaseName).toBe('past-projects');
    expect(context).toMatchObject({title: 'Curation Draft'});
  });

  it('exports Word through the word exporter', async () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector(
      '.project-grid-toolbar-cluster[aria-label="Export"]',
    ) as HTMLElement;

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Word'}));

    await waitFor(() => expect(exportMocks.exportProjectRowsWord).toHaveBeenCalledTimes(1));
    const [rowsArg, fileBaseName] = exportMocks.exportProjectRowsWord.mock.calls[0];
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(fileBaseName).toBe('past-projects');
  });
});
