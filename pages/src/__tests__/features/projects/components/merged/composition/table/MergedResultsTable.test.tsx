import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

// Desktop and mobile tables both render, so per-row content appears twice. Scope queries to the
// desktop table to get a single match.
const desktopTable = (container: HTMLElement) =>
  container.querySelector('.project-grid-table-wrap') as HTMLElement;

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

  it('select-all + Remove Selected only removes rows matching the active search, never hidden rows', async () => {
    const onDeleteRows = vi.fn();
    const {container} = render(
      <MergedResultsTable
        rows={makeItems([baseRow, addedRow])}
        onCreateShare={vi.fn()}
        onDeleteRow={vi.fn()}
        onDeleteRows={onDeleteRows}
        onUndoRows={vi.fn()}
        onResetRows={vi.fn()}
      />,
    );

    // Narrow the visible rows to just the "Irrigation Sensor" row; "Shared Project" is hidden.
    fireEvent.change(screen.getByLabelText('Search this list'), {target: {value: 'Irrigation'}});
    await waitFor(() =>
      expect(within(desktopTable(container)).queryByText('Shared Project')).not.toBeInTheDocument(),
    );

    const selectAll = within(desktopTable(container)).getByLabelText('Select all rows') as HTMLInputElement;
    fireEvent.click(selectAll);
    expect(selectAll).toBeChecked();

    fireEvent.click(screen.getByRole('button', {name: /remove selected/i}));

    expect(onDeleteRows).toHaveBeenCalledTimes(1);
    const removed = onDeleteRows.mock.calls[0][0];
    expect(removed).toHaveLength(1);
    expect(removed[0]).toMatchObject({project_title: 'Irrigation Sensor'});
  });

  it('removes only checked rows the search shows, keeping rows checked under an earlier search', async () => {
    const onDeleteRows = vi.fn();
    const {container} = render(
      <MergedResultsTable
        rows={makeItems([baseRow, addedRow])}
        onCreateShare={vi.fn()}
        onDeleteRow={vi.fn()}
        onDeleteRows={onDeleteRows}
        onUndoRows={vi.fn()}
        onResetRows={vi.fn()}
      />,
    );
    const search = screen.getByLabelText('Search this list');
    const desktop = () => within(desktopTable(container));

    // Check "Shared Project", then search for the other row: the first stays checked but hidden.
    fireEvent.click(desktop().getByLabelText('Select Shared Project'));
    fireEvent.change(search, {target: {value: 'Irrigation'}});
    await waitFor(() => expect(desktop().queryByText('Shared Project')).not.toBeInTheDocument());
    const removeSelected = screen.getByRole('button', {name: 'Remove Selected'});
    expect(removeSelected).toHaveAttribute('aria-disabled', 'true');

    fireEvent.click(desktop().getByLabelText('Select Irrigation Sensor'));
    fireEvent.click(removeSelected);

    expect(onDeleteRows).toHaveBeenCalledTimes(1);
    expect(onDeleteRows.mock.calls[0][0].map((row: ProjectGridRow) => row.project_title)).toEqual(['Irrigation Sensor']);
    fireEvent.change(search, {target: {value: ''}});
    expect(await desktop().findByLabelText('Select Shared Project')).toBeChecked();
  });

  it('clears the selection when select-all is toggled while everything visible is selected', () => {
    const {container} = render(
      <MergedResultsTable
        rows={makeItems([baseRow])}
        onCreateShare={vi.fn()}
        onDeleteRow={vi.fn()}
        onDeleteRows={vi.fn()}
        onUndoRows={vi.fn()}
        onResetRows={vi.fn()}
      />,
    );

    const selectAll = within(desktopTable(container)).getByLabelText('Select all rows') as HTMLInputElement;
    fireEvent.click(selectAll);
    expect(selectAll).toBeChecked();

    fireEvent.click(selectAll);
    expect(selectAll).not.toBeChecked();
  });

  it('cancels the reset merged results confirmation without resetting', () => {
    const onResetRows = vi.fn();

    render(
      <MergedResultsTable
        rows={makeItems()}
        onCreateShare={vi.fn()}
        onDeleteRow={vi.fn()}
        onDeleteRows={vi.fn()}
        onUndoRows={vi.fn()}
        onResetRows={onResetRows}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /clear draft/i}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: /cancel/i}));

    expect(onResetRows).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
