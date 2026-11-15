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

  it('lays out the saved list as a panel with its count, the table, the export and edit groups, and saving', () => {
    render(
      <MergedResultsTable
        id="saved"
        rows={makeItems([baseRow, addedRow])}
        onCreateShare={vi.fn()}
        onDeleteRow={vi.fn()}
        onDeleteRows={vi.fn()}
        onUndoRows={vi.fn()}
        onResetRows={vi.fn()}
      />,
    );

    const section = screen.getByRole('region', {name: 'Curation Draft'});
    expect(section).toHaveClass('itg-panel');
    expect(section.querySelector('.project-grid-card-count')).toHaveTextContent('2 projects in this draft');
    const editGroup = within(section).getByRole('group', {name: 'Edit list'});
    expect(within(editGroup).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Remove Selected',
      'Undo',
      'Clear Draft',
    ]);
    expect(within(editGroup).getByRole('button', {name: 'Remove Selected'})).toHaveAttribute('aria-disabled', 'true');
    expect(within(editGroup).getByRole('button', {name: 'Clear Draft'})).toHaveClass('itg-btn-danger');
    expect(within(section).getByRole('heading', {level: 3, name: 'Save this curation'})).toBeInTheDocument();
    expect(
      within(section).getByText('Saved curations are listed under My Curations, each with a link anyone can view.'),
    ).toBeInTheDocument();
    // Saving is offered at the top of the card, with a line saying the list is not saved yet, and again under
    // the note.
    const [headerSave, sectionSave] = within(section).getAllByRole('button', {name: 'Save Curation'});
    expect(headerSave.closest('.project-grid-card-header')).not.toBeNull();
    expect(within(section).getByText(/Not saved yet\. This browser keeps the draft until you save it\./)).toBeInTheDocument();
    expect(sectionSave.closest('.project-grid-share-actions')).not.toBeNull();
  });

  it('pages to and highlights the rows the latest save added', () => {
    const newer = Array.from({length: 5}, (_, index) => ({
      ...baseRow,
      semester_label: '2026 Spring',
      team_number: `N${index}`,
      project_title: `Newer ${index}`,
    }));
    const older = {...baseRow, semester_label: '2021 Fall', team_number: 'O1', project_title: 'Older Project'};
    const firstItems = createProjectGridItems(newer, 'first');
    const addedItems = createProjectGridItems([older], 'second');
    const {container, rerender} = render(
      <MergedResultsTable rows={firstItems} recentlyAdded={{keys: new Set(firstItems.map((row) => row.__key)), token: 1}} />,
    );
    expect(screen.queryByText('Page 2 of 2')).toBeNull();

    rerender(
      <MergedResultsTable
        rows={[...firstItems, ...addedItems]}
        recentlyAdded={{keys: new Set(addedItems.map((row) => row.__key)), token: 2}}
      />,
    );

    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    const olderRow = within(desktopTable(container)).getByText('Older Project').closest('tr') as HTMLElement;
    expect(olderRow).toHaveClass('is-new');
  });

  it('says when the merged-table search hides newly saved rows and can clear it', async () => {
    const firstItems = makeItems([baseRow]);
    const addedItems = createProjectGridItems([addedRow], 'second');
    const {rerender} = render(<MergedResultsTable rows={firstItems} />);
    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'Shared Project'}});

    rerender(
      <MergedResultsTable
        rows={[...firstItems, ...addedItems]}
        recentlyAdded={{keys: new Set(addedItems.map((row) => row.__key)), token: 1}}
      />,
    );

    expect(await screen.findByText(/1 newly added project is hidden by your search\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Clear Search'}));
    await waitFor(() => expect(screen.queryByText(/hidden by your search/)).toBeNull());
    expect(screen.getAllByText('Irrigation Sensor').length).toBeGreaterThan(0);
  });

  it('labels the rows the latest save added, not only by colour', () => {
    const items = makeItems([baseRow, addedRow]);
    const {container} = render(
      <MergedResultsTable rows={items} recentlyAdded={{keys: new Set([items[1].__key]), token: 1}} />,
    );

    const addedTitle = within(desktopTable(container)).getByText('Irrigation Sensor');
    expect(within(addedTitle.closest('td') as HTMLElement).getByText('New')).toBeInTheDocument();
    expect(within(desktopTable(container)).queryAllByText('New')).toHaveLength(1);
  });

  it('folds the saved list behind a disclosure for phones', () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} onCreateShare={vi.fn()} />);

    const toggle = screen.getByRole('button', {name: 'Show the 2 Projects'});
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const list = document.getElementById(toggle.getAttribute('aria-controls') as string);
    expect(list).not.toHaveClass('is-open');

    fireEvent.click(toggle);

    expect(screen.getByRole('button', {name: 'Hide the Projects'})).toHaveAttribute('aria-expanded', 'true');
    expect(list).toHaveClass('is-open');
  });

  it('heads a saved-results search with no matches one level under the card title (h3)', () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} onCreateShare={vi.fn()} title="Merged Results" />);

    fireEvent.change(screen.getByRole('searchbox', {name: 'Search this list'}), {target: {value: 'hydroponics'}});

    expect(screen.getByRole('heading', {level: 2, name: 'Merged Results'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 3, name: 'No projects match “hydroponics”'})).toBeInTheDocument();
  });
});
