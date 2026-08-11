import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/projectGrid';

const exportMocks = vi.hoisted(() => ({
  exportProjectRowsExcel: vi.fn(),
  exportProjectRowsPdf: vi.fn(),
  exportProjectRowsWord: vi.fn(),
}));

vi.mock('@/features/projects/components/export/excelExport', () => ({exportProjectRowsExcel: exportMocks.exportProjectRowsExcel}));
vi.mock('@/features/projects/components/export/pdfExport', () => ({exportProjectRowsPdf: exportMocks.exportProjectRowsPdf}));
vi.mock('@/features/projects/components/export/wordExport', () => ({exportProjectRowsWord: exportMocks.exportProjectRowsWord}));

const baseRow: ProjectGridRow = {
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: 'T01',
  team_name: 'Team Alpha',
  project_title: 'Archived Project',
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

const desktopTable = (container: HTMLElement) =>
  container.querySelector('.project-grid-table-wrap') as HTMLElement;

const exportCluster = (container: HTMLElement) =>
  container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]') as HTMLElement;

describe('MergedResultsTable', () => {
  beforeEach(() => {
    exportMocks.exportProjectRowsExcel.mockReset().mockResolvedValue(undefined);
    exportMocks.exportProjectRowsPdf.mockReset().mockResolvedValue(undefined);
    exportMocks.exportProjectRowsWord.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('offers only Excel, PDF, and Word exports', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} />);
    expect(within(exportCluster(container)).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'PDF',
      'Excel',
      'Microsoft Word',
    ]);
  });

  it('select-all and Remove Selected only remove rows matching the active search', async () => {
    const onDeleteRows = vi.fn();
    const {container} = render(
      <MergedResultsTable
        rows={makeItems([baseRow, addedRow])}
        onDeleteRow={vi.fn()}
        onDeleteRows={onDeleteRows}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/search merged results/i), {target: {value: 'Irrigation'}});
    await waitFor(() =>
      expect(within(desktopTable(container)).queryByText('Archived Project')).not.toBeInTheDocument(),
    );

    fireEvent.click(within(desktopTable(container)).getByLabelText('Select all rows'));
    fireEvent.click(screen.getByRole('button', {name: /remove selected/i}));

    expect(onDeleteRows).toHaveBeenCalledTimes(1);
    expect(onDeleteRows.mock.calls[0][0]).toHaveLength(1);
    expect(onDeleteRows.mock.calls[0][0][0]).toMatchObject({project_title: 'Irrigation Sensor'});
  });

  it('passes visible rows and the standard title to the chosen exporter', async () => {
    const {container} = render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} />);
    fireEvent.change(screen.getByPlaceholderText(/search merged results/i), {target: {value: 'Irrigation'}});
    fireEvent.click(within(exportCluster(container)).getByRole('button', {name: 'Excel'}));

    await waitFor(() => expect(exportMocks.exportProjectRowsExcel).toHaveBeenCalledTimes(1));
    const [rowsArg, fileBaseName, context] = exportMocks.exportProjectRowsExcel.mock.calls[0];
    expect(rowsArg).toHaveLength(1);
    expect(rowsArg[0]).toMatchObject({project_title: 'Irrigation Sensor'});
    expect(fileBaseName).toBe('past-projects');
    expect(context).toEqual({title: 'Saved Merged Results'});
  });

  it('surfaces an error message when an export fails', async () => {
    exportMocks.exportProjectRowsExcel.mockRejectedValueOnce(new Error('chunk load failed'));
    const {container} = render(<MergedResultsTable rows={makeItems()} />);
    fireEvent.click(within(exportCluster(container)).getByRole('button', {name: 'Excel'}));
    expect(await screen.findByText('Unable to export Excel. Please try again.')).toBeInTheDocument();
  });

  it('disables every export button when there are no rows', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([])} />);
    within(exportCluster(container)).getAllByRole('button').forEach((button) => expect(button).toBeDisabled());
  });

  it('confirms before resetting merged results', () => {
    const onResetRows = vi.fn();
    render(<MergedResultsTable rows={makeItems()} onResetRows={onResetRows} />);
    fireEvent.click(screen.getByRole('button', {name: 'Reset Merged Results'}));
    fireEvent.click(
      within(screen.getByRole('dialog', {name: 'Reset merged results?'})).getByRole('button', {
        name: 'Reset Merged Results',
      }),
    );
    expect(onResetRows).toHaveBeenCalledTimes(1);
  });

  it('shows the individual project URL in expanded desktop and mobile details', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([rowWithId])} />);
    fireEvent.click(within(desktopTable(container)).getByRole('button', {name: 'View'}));

    const expectedHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    const desktopLink = desktopTable(container).querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(desktopLink).toHaveAttribute('href', expectedHref);

    const mobileCards = container.querySelector('.project-grid-mobile-cards') as HTMLElement;
    const mobileLink = mobileCards.querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(mobileLink).toHaveAttribute('href', expectedHref);
  });

  it('exposes the current desktop sort direction to assistive technology', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} />);
    const table = desktopTable(container);
    const semesterHeader = within(table).getByRole('columnheader', {name: /year-semester/i});
    const titleHeader = within(table).getByRole('columnheader', {name: /project title/i});

    expect(semesterHeader).toHaveAttribute('aria-sort', 'descending');
    fireEvent.click(within(titleHeader).getByRole('button'));
    expect(titleHeader).toHaveAttribute('aria-sort', 'ascending');
  });

  it('lets an id-only row expand so its individual project URL is reachable', () => {
    const idOnlyRow: ProjectGridRow = {...rowWithId, abstract: '', student_names: ''};
    const {container} = render(<MergedResultsTable rows={makeItems([idOnlyRow])} />);
    const detailButton = within(desktopTable(container)).getByRole('button', {name: 'View'});
    expect(detailButton).toBeEnabled();
    fireEvent.click(detailButton);
    expect(desktopTable(container).querySelector('.project-grid-individual-link')).not.toBeNull();
  });

  it('does not show an individual link for legacy rows without an id', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} />);
    fireEvent.click(within(desktopTable(container)).getByRole('button', {name: 'View'}));
    expect(desktopTable(container).querySelector('.project-grid-individual-link')).toBeNull();
  });
});
