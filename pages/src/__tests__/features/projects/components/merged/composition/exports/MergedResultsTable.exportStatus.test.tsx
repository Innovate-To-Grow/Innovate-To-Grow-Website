
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

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

  it('runs one export at a time and says it is preparing it', async () => {
    let finishPdf!: () => void;
    exportMocks.exportProjectRowsPdf.mockReturnValueOnce(new Promise<void>((resolve) => { finishPdf = resolve; }));
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]') as HTMLElement;
    const pdf = within(exportCluster).getByRole('button', {name: 'PDF'});

    fireEvent.click(pdf);
    expect(screen.getByRole('status')).toHaveTextContent('Preparing PDF…');
    await waitFor(() => expect(exportMocks.exportProjectRowsPdf).toHaveBeenCalledTimes(1));
    expect(exportCluster).toHaveAttribute('aria-busy', 'true');
    expect(pdf).toHaveAttribute('aria-disabled', 'true');
    // Clicks while it runs (impatient, or on a slow connection) start nothing.
    fireEvent.click(pdf);
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Excel'}));

    await act(async () => finishPdf());
    expect(exportMocks.exportProjectRowsPdf).toHaveBeenCalledTimes(1);
    expect(exportMocks.exportProjectRowsExcel).not.toHaveBeenCalled();
    expect(exportCluster).not.toHaveAttribute('aria-busy');
    expect(screen.queryByText('Preparing PDF…')).toBeNull();
  });

  it('clears an earlier export failure once an export succeeds', async () => {
    exportMocks.exportProjectRowsWord.mockRejectedValueOnce(new Error('serialization failed'));
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]') as HTMLElement;

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Word'}));
    expect(await screen.findByText('Unable to export Microsoft Word. Please try again.')).toBeInTheDocument();
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Excel'}));

    await waitFor(() => expect(exportMocks.exportProjectRowsExcel).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText(/Unable to export/)).toBeNull());
  });

  it('asks for a reload, not a retry, when code an export needs did not download', async () => {
    // A stale tab after a deploy (the old chunk is gone), or a failed download: browsers keep the failed module.
    exportMocks.exportProjectRowsPdf.mockRejectedValueOnce(
      new TypeError('Failed to fetch dynamically imported module: https://i2g.example/assets/jspdf.es.min-OLD.js'),
    );
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]') as HTMLElement;

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'PDF'}));

    expect(
      await screen.findByText(
        'Unable to export PDF: part of this page did not download, often because the site was updated. ' +
          'Reload the page, then export again. Your curation draft is kept.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Please try again/)).toBeNull();
    expect(within(exportCluster).getByRole('button', {name: 'Reload Page'})).toBeInTheDocument();
  });

  it('drops the reload advice and its button once another export succeeds', async () => {
    exportMocks.exportProjectRowsPdf.mockRejectedValueOnce(
      new TypeError('Failed to fetch dynamically imported module: https://i2g.example/assets/jspdf.es.min-OLD.js'),
    );
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]') as HTMLElement;
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'PDF'}));
    expect(await within(exportCluster).findByRole('button', {name: 'Reload Page'})).toBeInTheDocument();

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Word'}));

    await waitFor(() => expect(exportMocks.exportProjectRowsWord).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText(/Unable to export/)).toBeNull());
    expect(within(exportCluster).queryByRole('button', {name: 'Reload Page'})).toBeNull();
  });
});
