
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

const normalizedBaseRow: ProjectGridRow = {...baseRow, semester_label: '2025 Spring'};
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

  it('lets an editable shared page save name changes', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);

    render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Original Name"
        note="Owner note"
        onUpdateShare={onUpdateShare}
      />,
    );

    // Each label is its own element beside the icon, so a translated page never leaves React a detached text node.
    const editButton = screen.getByRole('button', {name: 'Edit Name'});
    expect(within(editButton).getByText('Edit Name').tagName).toBe('SPAN');
    fireEvent.click(editButton);
    fireEvent.change(screen.getByLabelText('Curation name'), {target: {value: 'Updated Name'}});
    const saveButton = screen.getByRole('button', {name: 'Save Name'});
    expect(within(saveButton).getByText('Save Name').tagName).toBe('SPAN');
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([normalizedBaseRow], 'Updated Name', 'Owner note');
    });
    expect(await screen.findByText('Name updated.')).toBeInTheDocument();
  });

  it('lets an editable shared page clear the name so the backend can derive a default', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);

    render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Original Name"
        note="Owner note"
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /edit name/i}));
    fireEvent.change(screen.getByLabelText('Curation name'), {target: {value: '   '}});
    fireEvent.click(screen.getByRole('button', {name: /save name/i}));

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([normalizedBaseRow], '', 'Owner note');
    });
    expect(screen.queryByText('Name is required.')).toBeNull();
    expect(await screen.findByText('Name updated.')).toBeInTheDocument();
  });

  it('closes the title editor without saving when the name is unchanged', () => {
    const onUpdateShare = vi.fn();

    render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Original"
        note=""
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /edit name/i}));
    expect(screen.getByLabelText('Curation name')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /save name/i}));

    expect(screen.queryByLabelText('Curation name')).toBeNull();
    expect(onUpdateShare).not.toHaveBeenCalled();
  });

  it('saves a shared title with the Enter key', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);

    render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Original"
        note=""
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /edit name/i}));
    fireEvent.change(screen.getByLabelText('Curation name'), {target: {value: 'Renamed'}});
    fireEvent.keyDown(screen.getByLabelText('Curation name'), {key: 'Enter'});

    await waitFor(() => expect(onUpdateShare).toHaveBeenCalledWith([normalizedBaseRow], 'Renamed', ''));
  });

  it('closes the inline title editor when the title prop changes externally', () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);
    const {rerender} = render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="First"
        note=""
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /edit name/i}));
    expect(screen.getByLabelText('Curation name')).toBeInTheDocument();

    rerender(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Second"
        note=""
        onUpdateShare={onUpdateShare}
      />,
    );

    expect(screen.queryByLabelText('Curation name')).toBeNull();
  });
});
