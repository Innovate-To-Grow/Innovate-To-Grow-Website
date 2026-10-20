import {StrictMode} from 'react';
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/projectGrid';

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

vi.mock('@/features/projects/components/export/excelExport', () => ({
  exportProjectRowsExcel: exportMocks.exportProjectRowsExcel,
}));
vi.mock('@/features/projects/components/export/pdfExport', () => ({
  exportProjectRowsPdf: exportMocks.exportProjectRowsPdf,
}));
vi.mock('@/features/projects/components/export/wordExport', () => ({
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

const rowWithId: ProjectGridRow = {
  ...baseRow,
  id: '11111111-1111-4111-8111-111111111111',
};

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

  it('offers only Excel, PDF, and Word exports (no CSV)', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    expect(getExportButtonLabels(container)).toEqual(['PDF', 'Excel', 'Microsoft Word']);
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
    expect(await screen.findByText('Saved. Opening your curation...')).toBeInTheDocument();
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

  it('inserts visible project details and individual links into the share note', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');

    render(<MergedResultsTable rows={makeItems([rowWithId])} onCreateShare={onCreateShare} />);

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    fireEvent.click(screen.getByRole('button', {name: 'Insert projects into note'}));

    const expectedIndividualHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
    expect(noteEditor.textContent).toContain('Project Title: Shared Project');
    expect(noteEditor.textContent).toContain(`Individual Link: ${expectedIndividualHref}`);
    const insertedLink = noteEditor.querySelector('a');
    expect(insertedLink?.getAttribute('href')).toBe(expectedIndividualHref);

    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'Spring finalists'}});
    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    const noteArg = onCreateShare.mock.calls[0][2];
    expect(noteArg).toContain('Project Title');
    expect(noteArg).toContain(`<a href="${expectedIndividualHref}">`);
  });

  it('inserts curation content when the note editor was focused', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId])} onCreateShare={vi.fn()} />);

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    const insertButton = screen.getByRole('button', {name: 'Insert projects into note'});
    noteEditor.focus();
    expect(noteEditor).toHaveFocus();

    insertButton.focus();
    fireEvent.click(insertButton);

    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
    expect(noteEditor.textContent).toContain('Project Title: Shared Project');
  });

  it('excludes configured project fields from inserted note text', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId])} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: 'Choose fields'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Individual Link'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Abstract'}));
    fireEvent.click(screen.getByRole('button', {name: 'Insert projects into note'}));

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
    expect(noteEditor.textContent).toContain('Project Title: Shared Project');
    expect(noteEditor.textContent).not.toContain('Individual Link');
    expect(noteEditor.textContent).not.toContain('Abstract');
    expect(noteEditor.querySelector('a')).toBeNull();
  });

  it('updates the existing curated note block without overwriting manual note text', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId, addedRow])} onCreateShare={vi.fn()} />);

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    setRichTextEditorHtml(noteEditor, '<div>Manual intro</div>');
    fireEvent.click(screen.getByRole('button', {name: 'Insert projects into note'}));

    await waitFor(() => expect(noteEditor.textContent).toContain('Project 2'));
    expect(noteEditor.textContent).toContain('Manual intro');
    expect(noteEditor.querySelectorAll('[data-past-project-note-curation="project-summary"]')).toHaveLength(1);

    // Re-inserting keeps the manual intro and the existing curated block intact: projects already in
    // the block are not rebuilt or duplicated (they survive hand edits), so a single curation
    // container holds exactly one "Project 1" entry.
    fireEvent.click(screen.getByRole('button', {name: 'Insert projects into note'}));

    await waitFor(() => expect(noteEditor.textContent).toContain('Project 2'));
    expect(noteEditor.textContent).toContain('Manual intro');
    expect(noteEditor.textContent?.match(/Project 1/g)).toHaveLength(1);
    expect(noteEditor.querySelectorAll('[data-past-project-note-curation="project-summary"]')).toHaveLength(1);
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
    expect(context).toMatchObject({title: 'Saved Merged Results'});
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
    fireEvent.click(screen.getByRole('button', {name: 'Insert projects into note'}));
    expect(onNoteDraftChange).toHaveBeenLastCalledWith(expect.stringContaining('Kept note'));
    expect(onNoteDraftChange).toHaveBeenLastCalledWith(expect.stringContaining('<strong>Project Title:</strong> Shared Project'));

    fireEvent.click(screen.getAllByRole('button', {name: 'Save Curation'})[0]);
    expect(onCreateShare).toHaveBeenCalledWith(expect.any(Array), 'Kept name', 'Kept note');
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

    const section = screen.getByRole('region', {name: 'Saved Merged Results'});
    expect(section).toHaveClass('itg-panel');
    expect(section.querySelector('.project-grid-card-count')).toHaveTextContent('2 projects in this list');
    const editGroup = within(section).getByRole('group', {name: 'Edit list'});
    expect(within(editGroup).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Remove Selected',
      'Undo Merged Change',
      'Reset Merged Results',
    ]);
    expect(within(editGroup).getByRole('button', {name: 'Remove Selected'})).toBeDisabled();
    expect(within(editGroup).getByRole('button', {name: 'Reset Merged Results'})).toHaveClass('itg-btn-danger');
    expect(within(section).getByRole('heading', {level: 3, name: 'Save this curation'})).toBeInTheDocument();
    expect(
      within(section).getByText('Saved curations are listed under My Curations, each with a link anyone can view.'),
    ).toBeInTheDocument();
    // Saving is offered at the top of the card, with a line saying the list is not saved yet, and again under
    // the note.
    const [headerSave, sectionSave] = within(section).getAllByRole('button', {name: 'Save Curation'});
    expect(headerSave.closest('.project-grid-card-header')).not.toBeNull();
    expect(within(section).getByText(/Not saved yet\. This browser keeps the list until you save it\./)).toBeInTheDocument();
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

    expect(await screen.findByText(/1 newly saved project is hidden by your search\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Clear search'}));
    await waitFor(() => expect(screen.queryByText(/hidden by your search/)).toBeNull());
    expect(screen.getAllByText('Irrigation Sensor').length).toBeGreaterThan(0);
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

    expect(screen.getByRole('button', {name: 'Remove Selected'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Undo Merged Change'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Reset Merged Results'})).toBeDisabled();
    screen.getAllByRole('button', {name: 'Remove'}).forEach((button) => expect(button).toBeDisabled());

    await act(async () => finishShare('share-1'));
    expect(screen.getByRole('button', {name: 'Reset Merged Results'})).toBeEnabled();
    expect(onDeleteRows).not.toHaveBeenCalled();
  });

  it('says when its search narrows what saving and exports include', async () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} onCreateShare={vi.fn()} />);

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'Irrigation'}});

    expect(
      await screen.findByText(
        /Your search shows 1 of 2 saved projects\. Saving and exports include only the 1 it shows\./,
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Clear search'}));
    await waitFor(() => expect(screen.queryByText(/Your search shows/)).toBeNull());
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

  it('recovers from a failed share under StrictMode', async () => {
    const onCreateShare = vi.fn().mockRejectedValue(new Error('boom'));
    render(
      <StrictMode>
        <MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />
      </StrictMode>,
    );

    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    expect(await screen.findByText('Unable to save this curation. Please try again.')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Saving...'})).toBeNull();
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

  it('hides the share controls and shows a login hint for anonymous users', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});
    render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);

    expect(screen.queryByRole('button', {name: /save curation/i})).toBeNull();
    expect(screen.queryByLabelText(/curation name/i)).toBeNull();
    expect(screen.getByText(/to save this curation and get a link to share it/i)).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Sign in to save'}).getAttribute('href')).toMatch(/^\/login\?returnTo=/);
    // The sign-in link carries a returnTo so sign-in brings the visitor back to this page.
    const loginLink = screen.getByRole('link', {name: 'Sign in'});
    expect(loginLink.getAttribute('href')).toMatch(/^\/login\?returnTo=/);
  });

  it('renders the share link above the note in shared mode', async () => {
    const {container} = render(
      <MergedResultsTable rows={makeItems()} sharedMode note="Curated highlights" />,
    );

    const shareBlock = container.querySelector('.project-grid-share-result');
    expect(shareBlock).toHaveClass('itg-panel');
    expect(within(shareBlock as HTMLElement).getByRole('button', {name: 'Copy link'})).toBeInTheDocument();
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
    expect(getExportButtonLabels(container)).toEqual(['PDF', 'Excel', 'Microsoft Word']);
  });

  it('folds the saved list behind a disclosure for phones', () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} onCreateShare={vi.fn()} />);

    const toggle = screen.getByRole('button', {name: 'Show the 2 saved projects'});
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const list = document.getElementById(toggle.getAttribute('aria-controls') as string);
    expect(list).not.toHaveClass('is-open');

    fireEvent.click(toggle);

    expect(screen.getByRole('button', {name: 'Hide the saved projects'})).toHaveAttribute('aria-expanded', 'true');
    expect(list).toHaveClass('is-open');
  });

  it('heads a shared list search with no matches one level under the list title (h2)', () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} sharedMode title="Spring picks" />);

    fireEvent.change(screen.getByRole('searchbox', {name: 'Search this list'}), {target: {value: 'hydroponics'}});

    expect(screen.getByRole('heading', {level: 1, name: 'Spring picks'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 2, name: 'No projects match “hydroponics”'})).toBeInTheDocument();
  });

  it('heads a saved-results search with no matches one level under the card title (h3)', () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} onCreateShare={vi.fn()} title="Merged Results" />);

    fireEvent.change(screen.getByRole('searchbox', {name: 'Search this list'}), {target: {value: 'hydroponics'}});

    expect(screen.getByRole('heading', {level: 2, name: 'Merged Results'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 3, name: 'No projects match “hydroponics”'})).toBeInTheDocument();
  });

  it('shows a shared list without the phone disclosure', () => {
    render(<MergedResultsTable rows={makeItems()} sharedMode />);

    expect(screen.queryByRole('button', {name: /saved project/})).toBeNull();
  });

  it('heads a shared list with an eyebrow, the list name and when it was shared', () => {
    render(
      <MergedResultsTable
        rows={makeItems([baseRow, addedRow])}
        sharedMode
        title="Spring picks"
        sharedAt="2026-10-16T12:00:00Z"
      />,
    );

    expect(screen.getByText('Shared list · Past Projects')).toHaveClass('itg-eyebrow');
    expect(screen.getByRole('heading', {level: 1, name: 'Spring picks'})).toBeInTheDocument();
    expect(screen.getByText('2 projects · shared October 16, 2026')).toHaveClass('itg-page-meta');
  });

  it('leaves the date out of the meta line when the share has none', () => {
    const {container} = render(
      <MergedResultsTable rows={makeItems()} sharedMode title="Spring picks" sharedAt="not a date" />,
    );

    expect(container.querySelector('.project-grid-shared-header .itg-page-meta')).toHaveTextContent(/^1 project$/);
  });

  it('copies the shareable link with the Copy link button', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    try {
      render(<MergedResultsTable rows={makeItems()} sharedMode />);

      fireEvent.click(screen.getByRole('button', {name: 'Copy link'}));

      await waitFor(() => expect(writeText).toHaveBeenCalledWith(window.location.href));
      expect(await screen.findByRole('status')).toHaveTextContent('Shareable URL copied.');
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('does not render a note block in shared mode when note is empty', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} sharedMode note="" />);
    expect(container.querySelector('.project-grid-shared-note')).toBeNull();
  });

  it('confirms when the shareable URL is copied to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    try {
      render(<MergedResultsTable rows={makeItems()} sharedMode />);

      fireEvent.click(screen.getByLabelText('Shareable link'));

      await waitFor(() => expect(writeText).toHaveBeenCalledWith(window.location.href));
      expect(await screen.findByText('Shareable URL copied.')).toBeInTheDocument();
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('asks for a manual copy when no clipboard mechanism is available', async () => {
    // jsdom has neither navigator.clipboard nor document.execCommand — both paths fall through.
    render(<MergedResultsTable rows={makeItems()} sharedMode />);

    fireEvent.click(screen.getByLabelText('Shareable link'));

    expect(await screen.findByText('Unable to copy URL. Select the link and copy it manually.')).toBeInTheDocument();
  });

  it('links to the project page from expanded desktop and mobile details', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([rowWithId])} />);

    const desktopDetailsButton = within(desktopTable(container)).getByRole('button', {name: 'Details'});
    expect(desktopDetailsButton).toHaveAttribute('aria-expanded', 'false');
    const desktopDetailsId = desktopDetailsButton.getAttribute('aria-controls');
    expect(desktopDetailsId).toBeTruthy();

    fireEvent.click(desktopDetailsButton);
    expect(desktopDetailsButton).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById(desktopDetailsId as string)).not.toBeNull();

    const expectedHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    const desktopLink = desktopTable(container).querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(desktopLink).not.toBeNull();
    expect(desktopLink.getAttribute('href')).toBe(expectedHref);
    expect(desktopLink).toHaveTextContent('Open the project page');
    expect(desktopLink).toHaveAttribute('target', '_blank');
    expect(within(desktopTable(container)).getByRole('button', {name: 'Copy project link'})).toBeVisible();

    const mobileCards = container.querySelector('.project-grid-mobile-cards') as HTMLElement;
    const mobileLink = mobileCards.querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(mobileLink).not.toBeNull();
    expect(mobileLink.getAttribute('href')).toBe(expectedHref);
    expect(mobileLink).toHaveTextContent('Open the project page');
    const mobileDetailsButton = within(mobileCards).getByRole('button', {name: 'Hide details'});
    expect(mobileDetailsButton).toHaveAttribute('aria-expanded', 'true');
    const mobileDetailsId = mobileDetailsButton.getAttribute('aria-controls');
    expect(mobileDetailsId).toBeTruthy();
    expect(document.getElementById(mobileDetailsId as string)).not.toBeNull();
  });

  it('exposes the current desktop sort direction to assistive technology', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} />);
    const table = desktopTable(container);
    const semesterHeader = within(table).getByRole('columnheader', {name: 'Term'});
    const titleHeader = within(table).getByRole('columnheader', {name: 'Project'});

    expect(semesterHeader).toHaveAttribute('aria-sort', 'descending');
    expect(titleHeader).toHaveAttribute('aria-sort', 'none');

    fireEvent.click(within(titleHeader).getByRole('button'));

    expect(semesterHeader).toHaveAttribute('aria-sort', 'none');
    expect(titleHeader).toHaveAttribute('aria-sort', 'ascending');
  });

  it('lets an id-only row expand so its individual project URL is reachable', () => {
    const idOnlyRow: ProjectGridRow = {...rowWithId, abstract: '', student_names: ''};
    const {container} = render(<MergedResultsTable rows={makeItems([idOnlyRow])} />);
    const detailButton = within(desktopTable(container)).getByRole('button', {name: 'Details'});

    expect(detailButton).toBeEnabled();
    fireEvent.click(detailButton);

    const expectedHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    const desktopLink = desktopTable(container).querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(desktopLink).not.toBeNull();
    expect(desktopLink.getAttribute('href')).toBe(expectedHref);
    expect(desktopLink).toHaveTextContent('Open the project page');
  });

  it('does not show an individual link for legacy rows without an id', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} />);

    fireEvent.click(within(desktopTable(container)).getByRole('button', {name: 'Details'}));

    expect(desktopTable(container).querySelector('.project-grid-individual-link')).toBeNull();
    expect(within(desktopTable(container)).queryByRole('link')).toBeNull();
  });

  it('lets an editable shared page save note changes', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);

    render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Original Name"
        note="Original note"
        onUpdateShare={onUpdateShare}
      />,
    );

    const noteField = screen.getByRole('textbox', {name: 'Curation note'});
    expect(noteField).toHaveAttribute('aria-readonly', 'true');
    fireEvent.click(screen.getByRole('button', {name: /edit curation note/i}));
    expect(noteField).toHaveAttribute('aria-readonly', 'false');
    setRichTextEditorHtml(noteField, 'Updated note');
    fireEvent.click(screen.getByRole('button', {name: /save curation note/i}));

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([normalizedBaseRow], 'Original Name', 'Updated note');
    });
    expect(onUpdateShare.mock.calls[0]).toHaveLength(3);
    expect(await screen.findByText('Note updated.')).toBeInTheDocument();
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

    fireEvent.click(screen.getByRole('button', {name: /edit name/i}));
    fireEvent.change(screen.getByLabelText('Shared page name'), {target: {value: 'Updated Name'}});
    fireEvent.click(screen.getByRole('button', {name: /save name/i}));

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
    fireEvent.change(screen.getByLabelText('Shared page name'), {target: {value: '   '}});
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

    const undoButton = screen.getByRole('button', {name: /undo shared change/i});
    expect(undoButton).toBeDisabled();

    fireEvent.click(screen.getAllByRole('button', {name: /remove/i})[0]);

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([normalizedAddedRow], 'Original Name', 'Owner note');
    });
    // The button enables only after the post-await state commits (setSharedRowsUndo +
    // setIsSavingShareEdit(false)), which lands in a later microtask than the mock call above.
    await waitFor(() => expect(undoButton).toBeEnabled());

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

  it('keeps Remove All guarded for editable shared pages while the API requires one row', async () => {
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

    fireEvent.click(screen.getByRole('button', {name: /remove all/i}));
    const dialog = screen.getByRole('dialog', {name: /remove all projects/i});
    // Informational dialog: a single Close action, no confusing cancel alternative.
    expect(within(dialog).queryByRole('button', {name: /keep projects/i})).toBeNull();
    fireEvent.click(within(dialog).getByRole('button', {name: /close/i}));

    expect(onUpdateShare).not.toHaveBeenCalled();
    expect(await screen.findByText(/A shared page needs at least one project/i)).toBeInTheDocument();
  });

  it('expands all rows by default in shared mode so project details are visible', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} sharedMode note="See below" />);
    expect(within(desktopTable(container)).getByText(/A detailed project abstract\./)).toBeInTheDocument();
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
    expect(context).toMatchObject({title: 'Saved Merged Results'});
  });

  it('exports Microsoft Word through the word exporter', async () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector(
      '.project-grid-toolbar-cluster[aria-label="Export"]',
    ) as HTMLElement;

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Microsoft Word'}));

    await waitFor(() => expect(exportMocks.exportProjectRowsWord).toHaveBeenCalledTimes(1));
    const [rowsArg, fileBaseName] = exportMocks.exportProjectRowsWord.mock.calls[0];
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(fileBaseName).toBe('past-projects');
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

  it('re-includes an excluded field when the checkbox is toggled again', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId])} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: 'Choose fields'}));
    const individualLinkCheckbox = screen.getByRole('checkbox', {name: 'Individual Link'});
    fireEvent.click(individualLinkCheckbox);
    fireEvent.click(individualLinkCheckbox);
    fireEvent.click(screen.getByRole('button', {name: 'Insert projects into note'}));

    const noteEditor = screen.getByRole('textbox', {name: /curation note/i});
    await waitFor(() => expect(noteEditor.textContent).toContain('Individual Link'));
  });

  it('inserts projects into the shared note while editing', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);
    render(
      <MergedResultsTable
        rows={makeItems([rowWithId])}
        sharedMode
        editable
        title="Shared"
        note=""
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /edit curation note/i}));
    const noteEditor = screen.getByRole('textbox', {name: 'Curation note'});
    // Clicking the insert button moves focus in a real browser; mirror that so the
    // editor's focus guard does not suppress the inserted value rewrite.
    const insertButton = screen.getByRole('button', {name: 'Insert projects into note'});
    insertButton.focus();
    fireEvent.click(insertButton);

    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
  });

  it('copies the share URL via document.execCommand when no async clipboard exists', async () => {
    Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, 'execCommand', {value: execCommand, configurable: true, writable: true});
    try {
      render(<MergedResultsTable rows={makeItems()} sharedMode />);

      fireEvent.click(screen.getByLabelText('Shareable link'));

      expect(await screen.findByText('Shareable URL copied.')).toBeInTheDocument();
      expect(execCommand).toHaveBeenCalledWith('copy');
    } finally {
      Object.defineProperty(document, 'execCommand', {value: undefined, configurable: true, writable: true});
    }
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
    fireEvent.change(screen.getByLabelText('Shared page name'), {target: {value: 'New Name'}});
    fireEvent.click(screen.getByRole('button', {name: /save name/i}));

    expect(
      await screen.findByText('Unable to update this shared page. Please try again.'),
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
    expect(screen.getByLabelText('Shared page name')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /save name/i}));

    expect(screen.queryByLabelText('Shared page name')).toBeNull();
    expect(onUpdateShare).not.toHaveBeenCalled();
  });

  it('closes the note editor without saving when the note is unchanged', () => {
    const onUpdateShare = vi.fn();

    render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Shared"
        note="Same note"
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /edit curation note/i}));
    fireEvent.click(screen.getByRole('button', {name: /save curation note/i}));

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

    expect(await screen.findByText('A shared page needs at least one project.')).toBeInTheDocument();
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
    fireEvent.change(screen.getByLabelText('Shared page name'), {target: {value: 'Renamed'}});
    fireEvent.keyDown(screen.getByLabelText('Shared page name'), {key: 'Enter'});

    await waitFor(() => expect(onUpdateShare).toHaveBeenCalledWith([normalizedBaseRow], 'Renamed', ''));
  });

  it('copies the share URL when the input is focused', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    try {
      render(<MergedResultsTable rows={makeItems()} sharedMode />);

      fireEvent.focus(screen.getByLabelText('Shareable link'));

      await waitFor(() => expect(writeText).toHaveBeenCalledWith(window.location.href));
      expect(await screen.findByText('Shareable URL copied.')).toBeInTheDocument();
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
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

    fireEvent.click(screen.getByRole('button', {name: /reset merged results/i}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: /cancel/i}));

    expect(onResetRows).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('closes the inline note editor when the note prop changes externally', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);
    const {rerender} = render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Shared"
        note="first"
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /edit curation note/i}));
    expect(screen.getByRole('textbox', {name: 'Curation note'})).toHaveAttribute('aria-readonly', 'false');

    rerender(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Shared"
        note="second"
        onUpdateShare={onUpdateShare}
      />,
    );

    await waitFor(() =>
      expect(screen.getByRole('textbox', {name: 'Curation note'})).toHaveAttribute('aria-readonly', 'true'),
    );
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
    expect(screen.getByLabelText('Shared page name')).toBeInTheDocument();

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

    expect(screen.queryByLabelText('Shared page name')).toBeNull();
  });
});
