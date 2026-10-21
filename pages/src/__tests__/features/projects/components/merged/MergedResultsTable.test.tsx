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

const rowWithId: ProjectGridRow = {
  ...baseRow,
  id: '11111111-1111-4111-8111-111111111111',
};

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

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

  it('heads a saved-results search with no matches one level under the card title (h3)', () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} onCreateShare={vi.fn()} title="Merged Results" />);

    fireEvent.change(screen.getByRole('searchbox', {name: 'Search this list'}), {target: {value: 'hydroponics'}});

    expect(screen.getByRole('heading', {level: 2, name: 'Merged Results'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 3, name: 'No projects match “hydroponics”'})).toBeInTheDocument();
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
});
