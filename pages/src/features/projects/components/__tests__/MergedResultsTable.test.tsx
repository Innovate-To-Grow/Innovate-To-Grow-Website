import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '../MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '../projectGrid';

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

vi.mock('../export', () => exportMocks);

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

    fireEvent.change(screen.getByLabelText(/name this curation/i), {target: {value: 'Spring finalists'}});
    setRichTextEditorHtml(
      screen.getByRole('textbox', {name: /add a curation note/i}),
      'Review these with the team',
    );
    fireEvent.click(screen.getAllByRole('button', {name: /get shareable url/i})[0]);

    expect(onCreateShare).toHaveBeenCalledTimes(1);
    const [rowsArg, nameArg, noteArg] = onCreateShare.mock.calls[0];
    expect(onCreateShare.mock.calls[0]).toHaveLength(3); // no detailsText 4th arg
    expect(nameArg).toBe('Spring finalists');
    expect(noteArg).toBe('Review these with the team');
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(await screen.findByText('Opening shareable link...')).toBeInTheDocument();
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
    fireEvent.change(screen.getByPlaceholderText(/search merged results/i), {target: {value: 'Irrigation'}});
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

    const noteEditor = screen.getByRole('textbox', {name: /add a curation note/i});
    fireEvent.click(screen.getByRole('button', {name: 'Insert projects into note'}));

    const expectedIndividualHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
    expect(noteEditor.textContent).toContain('Project Title: Shared Project');
    expect(noteEditor.textContent).toContain(`Individual Link: ${expectedIndividualHref}`);
    const insertedLink = noteEditor.querySelector('a');
    expect(insertedLink?.getAttribute('href')).toBe(expectedIndividualHref);

    fireEvent.change(screen.getByLabelText(/name this curation/i), {target: {value: 'Spring finalists'}});
    fireEvent.click(screen.getAllByRole('button', {name: /get shareable url/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    const noteArg = onCreateShare.mock.calls[0][2];
    expect(noteArg).toContain('Project Title');
    expect(noteArg).toContain(`<a href="${expectedIndividualHref}">`);
  });

  it('inserts curation content when the note editor was focused', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId])} onCreateShare={vi.fn()} />);

    const noteEditor = screen.getByRole('textbox', {name: /add a curation note/i});
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

    fireEvent.click(screen.getByRole('button', {name: 'Project insert settings'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Individual Link'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Abstract'}));
    fireEvent.click(screen.getByRole('button', {name: 'Insert projects into note'}));

    const noteEditor = screen.getByRole('textbox', {name: /add a curation note/i});
    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
    expect(noteEditor.textContent).toContain('Project Title: Shared Project');
    expect(noteEditor.textContent).not.toContain('Individual Link');
    expect(noteEditor.textContent).not.toContain('Abstract');
    expect(noteEditor.querySelector('a')).toBeNull();
  });

  it('updates the existing curated note block without overwriting manual note text', async () => {
    render(<MergedResultsTable rows={makeItems([rowWithId, addedRow])} onCreateShare={vi.fn()} />);

    const noteEditor = screen.getByRole('textbox', {name: /add a curation note/i});
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

  it('enables the share button with rows even when the name is blank', () => {
    // The curation name is optional now — the backend derives one from the content. So the share
    // button is enabled whenever there are rows, and a blank name is passed through as an empty string.
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    const button = screen.getAllByRole('button', {name: /get shareable url/i})[0];
    expect(button).toBeEnabled();

    fireEvent.click(button);

    expect(onCreateShare).toHaveBeenCalledTimes(1);
    expect(onCreateShare.mock.calls[0][1]).toBe('');
  });

  it('passes the visible rows and export context to the chosen exporter', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    const exportCluster = container.querySelector(
      '.project-grid-toolbar-cluster[aria-label="Export"]',
    ) as HTMLElement;

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Excel'}));

    expect(exportMocks.exportProjectRowsExcel).toHaveBeenCalledTimes(1);
    const [rowsArg, fileBaseName, context] = exportMocks.exportProjectRowsExcel.mock.calls[0];
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(fileBaseName).toBe('past-projects');
    expect(context).toMatchObject({title: 'Saved Merged Results'});
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
    fireEvent.change(screen.getByLabelText(/name this curation/i), {target: {value: 'Filtered'}});
    fireEvent.click(screen.getAllByRole('button', {name: /get shareable url/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    const rowsArg = onCreateShare.mock.calls[0][0];
    expect(rowsArg).toHaveLength(1);
    expect(rowsArg[0]).toMatchObject({project_title: 'Irrigation Sensor'});
  });

  it('exports the full shared snapshot even when the viewer has filtered the table', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} sharedMode />);

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'Irrigation'}});
    const exportCluster = container.querySelector(
      '.project-grid-toolbar-cluster[aria-label="Export"]',
    ) as HTMLElement;
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Excel'}));

    expect(exportMocks.exportProjectRowsExcel).toHaveBeenCalledTimes(1);
    expect(exportMocks.exportProjectRowsExcel.mock.calls[0][0]).toHaveLength(2);
  });

  it('searches only the saved rows in a shared merged-results table', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} sharedMode />);

    const search = screen.getByRole('searchbox');
    expect(search).toHaveAttribute('placeholder', 'Search saved results...');
    fireEvent.change(search, {target: {value: 'Blue Diamond'}});

    expect(within(desktopTable(container)).getByText('Irrigation Sensor')).toBeInTheDocument();
    expect(within(desktopTable(container)).queryByText('Shared Project')).toBeNull();
    expect(screen.queryByText('Cascade Cooler Pouch Outfeed')).toBeNull();
  });

  it('hides the share controls and shows a login hint for anonymous users', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});
    render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);

    expect(screen.queryByRole('button', {name: /get shareable url/i})).toBeNull();
    expect(screen.queryByLabelText(/name this curation/i)).toBeNull();
    expect(screen.getByText(/to create a shareable link/i)).toBeInTheDocument();
    // The login link carries a returnTo so sign-in brings the visitor back to this page.
    const loginLink = screen.getByRole('link', {name: 'Log in'});
    expect(loginLink.getAttribute('href')).toMatch(/^\/login\?returnTo=/);
  });

  it('renders the share link above the note in shared mode', async () => {
    const {container} = render(
      <MergedResultsTable rows={makeItems()} sharedMode note="Curated highlights" />,
    );

    const shareBlock = await screen.findByRole('status');
    const noteBlock = container.querySelector('.project-grid-shared-note');
    expect(noteBlock).not.toBeNull();
    expect(screen.getByText('Curated highlights')).toBeInTheDocument();
    expect(screen.getByLabelText('Shareable URL')).toBeInTheDocument();

    const headerBlocks = Array.from(
      container.querySelectorAll('.project-grid-share-result, .project-grid-shared-note'),
    );
    expect(headerBlocks[0]).toBe(shareBlock);
    expect(headerBlocks[1]).toBe(noteBlock);

    // No create controls and no combined "Past Projects Detail" editor in shared mode.
    expect(screen.queryByRole('button', {name: /get shareable url/i})).toBeNull();
    expect(screen.queryByRole('textbox', {name: 'Past Projects Detail'})).toBeNull();
    expect(getExportButtonLabels(container)).toEqual(['PDF', 'Excel', 'Microsoft Word']);
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

      fireEvent.click(screen.getByLabelText('Shareable URL'));

      await waitFor(() => expect(writeText).toHaveBeenCalledWith(window.location.href));
      expect(await screen.findByText('Shareable URL copied.')).toBeInTheDocument();
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('asks for a manual copy when no clipboard mechanism is available', async () => {
    // jsdom has neither navigator.clipboard nor document.execCommand — both paths fall through.
    render(<MergedResultsTable rows={makeItems()} sharedMode />);

    fireEvent.click(screen.getByLabelText('Shareable URL'));

    expect(await screen.findByText('Unable to copy URL. Select the link and copy it manually.')).toBeInTheDocument();
  });

  it('shows the individual project URL in expanded desktop and mobile details', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([rowWithId])} />);

    fireEvent.click(within(desktopTable(container)).getByRole('button', {name: 'View'}));

    const expectedHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    const desktopLink = desktopTable(container).querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(desktopLink).not.toBeNull();
    expect(desktopLink.getAttribute('href')).toBe(expectedHref);
    expect(desktopLink).toHaveTextContent(expectedHref);
    expect(desktopLink).toBeVisible();
    expect(within(desktopTable(container)).getByText('Individual Project URL')).toBeVisible();

    const mobileCards = container.querySelector('.project-grid-mobile-cards') as HTMLElement;
    const mobileLink = mobileCards.querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(mobileLink).not.toBeNull();
    expect(mobileLink.getAttribute('href')).toBe(expectedHref);
    expect(mobileLink).toHaveTextContent(expectedHref);
    expect(mobileLink).toBeVisible();
    expect(within(mobileCards).getByText('Individual Project URL')).toBeVisible();
  });

  it('lets an id-only row expand so its individual project URL is reachable', () => {
    const idOnlyRow: ProjectGridRow = {...rowWithId, abstract: '', student_names: ''};
    const {container} = render(<MergedResultsTable rows={makeItems([idOnlyRow])} />);
    const detailButton = within(desktopTable(container)).getByRole('button', {name: 'View'});

    expect(detailButton).toBeEnabled();
    fireEvent.click(detailButton);

    const expectedHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    const desktopLink = desktopTable(container).querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(desktopLink).not.toBeNull();
    expect(desktopLink.getAttribute('href')).toBe(expectedHref);
    expect(desktopLink).toHaveTextContent(expectedHref);
  });

  it('does not show an individual link for legacy rows without an id', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} />);

    fireEvent.click(within(desktopTable(container)).getByRole('button', {name: 'View'}));

    expect(desktopTable(container).querySelector('.project-grid-individual-link')).toBeNull();
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
});
