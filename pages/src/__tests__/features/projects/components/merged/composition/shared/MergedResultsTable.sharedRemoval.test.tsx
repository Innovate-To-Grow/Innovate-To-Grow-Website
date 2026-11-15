
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

const normalizedBaseRow: ProjectGridRow = {...baseRow, semester_label: '2025 Spring'};
const normalizedAddedRow: ProjectGridRow = {...addedRow, semester_label: '2025 Spring'};

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

describe('MergedResultsTable in shared mode', () => {
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

  it('lets an editable shared page remove a project', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);

    render(
      <MergedResultsTable
        rows={makeItems([baseRow, addedRow])}
        sharedMode
        editable
        title="Original Name"
        note="Owner note"
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getAllByRole('button', {name: /remove/i})[0]);

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([normalizedAddedRow], 'Original Name', 'Owner note');
    });
    expect(await screen.findByText('Project removed.')).toBeInTheDocument();
  });

  it('lets an editable shared page undo the latest project removal', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);

    render(
      <MergedResultsTable
        rows={makeItems([baseRow, addedRow])}
        sharedMode
        editable
        title="Original Name"
        note="Owner note"
        onUpdateShare={onUpdateShare}
      />,
    );

    const undoButton = screen.getByRole('button', {name: /^undo$/i});
    expect(undoButton).toHaveAttribute('aria-disabled', 'true');

    fireEvent.click(screen.getAllByRole('button', {name: /remove/i})[0]);

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([normalizedAddedRow], 'Original Name', 'Owner note');
    });
    // The button enables only after the post-await state commits (setSharedRowsUndo +
    // setIsSavingShareEdit(false)), which lands in a later microtask than the mock call above.
    await waitFor(() => expect(undoButton).not.toHaveAttribute('aria-disabled'));

    fireEvent.click(undoButton);

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenLastCalledWith(
        [normalizedBaseRow, normalizedAddedRow],
        'Original Name',
        'Owner note',
      );
    });
    expect(await screen.findByText('Change undone.')).toBeInTheDocument();
  });

  it('offers its owner no "remove all", which a curation (at least one project) could never do', () => {
    render(
      <MergedResultsTable
        rows={makeItems([baseRow, addedRow])}
        sharedMode
        editable
        title="Original Name"
        note="Owner note"
        onUpdateShare={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const editGroup = screen.getByRole('group', {name: 'Edit list'});
    expect(within(editGroup).getAllByRole('button').map((button) => button.textContent)).toEqual(['Undo']);
    expect(screen.queryByRole('button', {name: /remove all/i})).toBeNull();
  });

  it('surfaces a failure message when a shared update is rejected', async () => {
    const onUpdateShare = vi.fn().mockRejectedValue(new Error('boom'));

    render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Original"
        note="Note"
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /edit name/i}));
    fireEvent.change(screen.getByLabelText('Curation name'), {target: {value: 'New Name'}});
    fireEvent.click(screen.getByRole('button', {name: /save name/i}));

    expect(
      await screen.findByText('Unable to update this curation. Please try again.'),
    ).toBeInTheDocument();
  });

  it('refuses to remove the final project from a shared page', async () => {
    const onUpdateShare = vi.fn();

    render(
      <MergedResultsTable
        rows={makeItems([baseRow])}
        sharedMode
        editable
        title="Shared"
        note=""
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getAllByRole('button', {name: /remove/i})[0]);

    expect(await screen.findByText('A curation needs at least one project.')).toBeInTheDocument();
    expect(onUpdateShare).not.toHaveBeenCalled();
  });
});
