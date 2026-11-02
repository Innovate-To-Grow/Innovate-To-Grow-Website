
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

const getExportButtonLabels = (container: HTMLElement) => {
  const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]');
  expect(exportCluster).not.toBeNull();
  return within(exportCluster as HTMLElement).getAllByRole('button').map((button) => button.textContent);
};

// Desktop and mobile tables both render, so per-row content appears twice. Scope queries to the
// desktop table to get a single match.
const desktopTable = (container: HTMLElement) =>
  container.querySelector('.project-grid-table-wrap') as HTMLElement;

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

  it('exports the full shared snapshot even when the viewer has filtered the table', async () => {
    const {container} = render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} sharedMode />);

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'Irrigation'}});
    const exportCluster = container.querySelector(
      '.project-grid-toolbar-cluster[aria-label="Export"]',
    ) as HTMLElement;
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Excel'}));

    await waitFor(() => expect(exportMocks.exportProjectRowsExcel).toHaveBeenCalledTimes(1));
    expect(exportMocks.exportProjectRowsExcel.mock.calls[0][0]).toHaveLength(2);
  });

  it('searches only the saved rows in a shared merged-results table', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} sharedMode />);

    const search = screen.getByRole('searchbox', {name: 'Search this list'});
    expect(search).toHaveAttribute('placeholder', 'Team, project, organization…');
    fireEvent.change(search, {target: {value: 'Blue Diamond'}});

    expect(within(desktopTable(container)).getByText('Irrigation Sensor')).toBeInTheDocument();
    expect(within(desktopTable(container)).queryByText('Shared Project')).toBeNull();
    expect(screen.queryByText('Cascade Cooler Pouch Outfeed')).toBeNull();
  });

  it('renders the share link above the note in shared mode', async () => {
    const {container} = render(
      <MergedResultsTable rows={makeItems()} sharedMode note="Curated highlights" />,
    );

    const shareBlock = container.querySelector('.project-grid-share-result');
    expect(shareBlock).toHaveClass('itg-panel');
    expect(within(shareBlock as HTMLElement).getByRole('button', {name: 'Copy Link'})).toBeInTheDocument();
    const noteBlock = container.querySelector('.project-grid-shared-note');
    expect(noteBlock).not.toBeNull();
    expect(screen.getByText('Curated highlights')).toBeInTheDocument();
    expect(screen.getByLabelText('Shareable link')).toBeInTheDocument();

    const headerBlocks = Array.from(
      container.querySelectorAll('.project-grid-share-result, .project-grid-shared-note'),
    );
    expect(headerBlocks[0]).toBe(shareBlock);
    expect(headerBlocks[1]).toBe(noteBlock);

    // No create controls and no combined "Past Projects Detail" editor in shared mode.
    expect(screen.queryByRole('button', {name: /save curation/i})).toBeNull();
    expect(screen.queryByRole('textbox', {name: 'Past Projects Detail'})).toBeNull();
    expect(getExportButtonLabels(container)).toEqual(['PDF', 'Excel', 'Word']);
  });

  it('heads a shared list search with no matches one level under the list title (h2)', () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} sharedMode title="Spring picks" />);

    fireEvent.change(screen.getByRole('searchbox', {name: 'Search this list'}), {target: {value: 'hydroponics'}});

    expect(screen.getByRole('heading', {level: 1, name: 'Spring picks'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 2, name: 'No projects match “hydroponics”'})).toBeInTheDocument();
  });

  it('shows a shared list without the phone disclosure', () => {
    render(<MergedResultsTable rows={makeItems()} sharedMode />);

    expect(screen.queryByRole('button', {name: /^show the/i})).toBeNull();
  });

  it('heads a shared list with an eyebrow, the list name, who curated it and when it was shared', () => {
    render(
      <MergedResultsTable
        rows={makeItems([baseRow, addedRow])}
        sharedMode
        title="Spring picks"
        sharedAt="2026-10-16T12:00:00Z"
      />,
    );

    expect(screen.getByText('Curation · Past Projects')).toHaveClass('itg-eyebrow');
    expect(screen.getByRole('heading', {level: 1, name: 'Spring picks'})).toBeInTheDocument();
    // A member wrote the name and note: the page says so rather than reading as an official record.
    expect(screen.getByText('Curated by a site member · 2 projects · shared October 16, 2026')).toHaveClass(
      'itg-page-meta',
    );
  });

  it('leaves the date out of the meta line when the share has none', () => {
    const {container} = render(
      <MergedResultsTable rows={makeItems()} sharedMode title="Spring picks" sharedAt="not a date" />,
    );

    expect(container.querySelector('.project-grid-shared-header .itg-page-meta')).toHaveTextContent(
      /^Curated by a site member · 1 project$/,
    );
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

  it('opens a shared list with every row collapsed, as every other list does', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} sharedMode note="See below" />);

    expect(container.querySelector('.project-grid-detail-row')).toBeNull();
    expect(within(desktopTable(container)).queryByText(/A detailed project abstract\./)).toBeNull();
    const toggle = screen.getByRole('button', {name: 'View All Details'});

    // View All Details still opens them all.
    fireEvent.click(toggle);
    expect(container.querySelectorAll('.project-grid-detail-row')).toHaveLength(2);
    expect(within(desktopTable(container)).getAllByText(/A detailed project abstract\./)).toHaveLength(2);
    expect(toggle).toHaveTextContent('Hide All Details');
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
