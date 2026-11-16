import {StrictMode} from 'react';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
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

const rowWithId: ProjectGridRow = {
  ...baseRow,
  id: '11111111-1111-4111-8111-111111111111',
};

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

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

  it('enables Save Curation with rows even when the name is blank', () => {
    // The curation name is optional now — the backend derives one from the content. So the share
    // button is enabled whenever there are rows, and a blank name is passed through as an empty string.
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    const button = screen.getAllByRole('button', {name: /save curation/i})[0];
    expect(button).toBeEnabled();

    fireEvent.click(button);

    expect(onCreateShare).toHaveBeenCalledTimes(1);
    expect(onCreateShare.mock.calls[0][1]).toBe('');
  });

  it('explains how an unnamed curation will be titled', () => {
    render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);

    const name = screen.getByLabelText(/curation name/i);
    expect(name).toHaveAccessibleName('Curation name (optional)');
    expect(name).toHaveAttribute('placeholder', 'Past Project Curation');
    expect(name).toHaveAccessibleDescription('Leave it blank to use the first line of your note.');
  });

  it('leaves the name and note to the builder when it keeps them', () => {
    const onNameDraftChange = vi.fn();
    const onNoteDraftChange = vi.fn();
    const onCreateShare = vi.fn().mockResolvedValue('share-1');
    render(
      <MergedResultsTable
        rows={makeItems([rowWithId])}
        onCreateShare={onCreateShare}
        nameDraft="Kept name"
        noteDraft="Kept note"
        onNameDraftChange={onNameDraftChange}
        onNoteDraftChange={onNoteDraftChange}
      />,
    );

    expect(screen.getByLabelText(/curation name/i)).toHaveValue('Kept name');
    expect(screen.getByRole('textbox', {name: /curation note/i})).toHaveTextContent('Kept note');
    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'New name'}});
    expect(onNameDraftChange).toHaveBeenCalledWith('New name');
    fireEvent.click(screen.getByRole('button', {name: 'Insert Projects into Note'}));
    expect(onNoteDraftChange).toHaveBeenLastCalledWith(expect.stringContaining('Kept note'));
    expect(onNoteDraftChange).toHaveBeenLastCalledWith(expect.stringContaining('<strong>Project Title:</strong> Shared Project'));

    fireEvent.click(screen.getAllByRole('button', {name: 'Save Curation'})[0]);
    expect(onCreateShare).toHaveBeenCalledWith(expect.any(Array), 'Kept name', 'Kept note');
  });

  it('waits for saves still loading before the curation can be saved', () => {
    const onCreateShare = vi.fn();
    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} pendingSaveCount={1} />);

    screen.getAllByRole('button', {name: /save curation/i}).forEach((button) => expect(button).toBeDisabled());
    const pending = screen.getByText(/Waiting for projects to finish saving/);
    expect(pending).toHaveAttribute('role', 'status');
    // Beside the button, not on a line of its own.
    expect(pending.closest('.project-grid-share-actions')).not.toBeNull();
  });

  it('keeps the saved rows as they are while the curation is being saved', async () => {
    let finishShare!: (value: string) => void;
    const onCreateShare = vi.fn(() => new Promise<string>((resolve) => { finishShare = resolve; }));
    const onDeleteRows = vi.fn();
    render(
      <MergedResultsTable
        rows={makeItems([baseRow, addedRow])}
        onCreateShare={onCreateShare}
        onDeleteRows={onDeleteRows}
        canUndoRows
        onUndoRows={vi.fn()}
        onResetRows={vi.fn()}
      />,
    );
    fireEvent.click(screen.getAllByLabelText(/^Select /)[1]);
    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    expect(screen.getByRole('button', {name: 'Remove Selected'})).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('button', {name: 'Undo'})).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('button', {name: 'Clear Draft'})).toHaveAttribute('aria-disabled', 'true');
    screen
      .getAllByRole('button', {name: /^Remove (Shared Project|Irrigation Sensor)$/})
      .forEach((button) => expect(button).toBeDisabled());

    await act(async () => finishShare('share-1'));
    expect(screen.getByRole('button', {name: 'Clear Draft'})).not.toHaveAttribute('aria-disabled');
    expect(onDeleteRows).not.toHaveBeenCalled();
  });

  it('says when its search narrows what saving and exports include', async () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} onCreateShare={vi.fn()} />);

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'Irrigation'}});

    expect(
      await screen.findByText(
        /Your search shows 1 of the 2 projects in this draft\. Saving and exports include only the 1 it shows; after saving, 1 other project stays in this draft\./,
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Clear Search'}));
    await waitFor(() => expect(screen.queryByText(/Your search shows/)).toBeNull());
  });

  it('recovers from a failed share under StrictMode', async () => {
    const onCreateShare = vi.fn().mockRejectedValue(new Error('boom'));
    render(
      <StrictMode>
        <MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />
      </StrictMode>,
    );

    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    expect(await screen.findByText('Unable to save this curation. Please try again.')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Saving…'})).toBeNull();
  });
});
