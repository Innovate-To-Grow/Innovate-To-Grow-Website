import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from './MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from './projectGrid';

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

vi.mock('./export', () => exportMocks);

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

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'Spring finalists'}});
    setRichTextEditorHtml(
      screen.getByRole('textbox', {name: /add a note/i}),
      'Review these with the team',
    );
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    expect(onCreateShare).toHaveBeenCalledTimes(1);
    const [rowsArg, nameArg, noteArg] = onCreateShare.mock.calls[0];
    expect(onCreateShare.mock.calls[0]).toHaveLength(3); // no detailsText 4th arg
    expect(nameArg).toBe('Spring finalists');
    expect(noteArg).toBe('Review these with the team');
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(await screen.findByText('Opening shareable link...')).toBeInTheDocument();
  });

  it('keeps the share button disabled until a name is entered', () => {
    const onCreateShare = vi.fn();
    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    const button = screen.getByRole('button', {name: /get shareable url/i});
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'Named'}});
    expect(button).toBeEnabled();
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
    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'Filtered'}});
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

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

  it('hides the share controls and shows a login hint for anonymous users', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});
    render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);

    expect(screen.queryByRole('button', {name: /get shareable url/i})).toBeNull();
    expect(screen.queryByLabelText(/name this shared link/i)).toBeNull();
    expect(screen.getByText(/to create a shareable link/i)).toBeInTheDocument();
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

  it('loads the individual link in expanded desktop and mobile details without displaying it', () => {
    const {container} = render(<MergedResultsTable rows={makeItems([rowWithId])} />);

    fireEvent.click(within(desktopTable(container)).getByRole('button', {name: 'View'}));

    const expectedHref = `/past-projects/project/${rowWithId.id}`;
    const desktopLink = desktopTable(container).querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(desktopLink).not.toBeNull();
    expect(desktopLink.getAttribute('href')).toBe(expectedHref);
    expect(desktopLink.tabIndex).toBe(-1);
    expect(desktopLink).not.toBeVisible();

    const mobileCards = container.querySelector('.project-grid-mobile-cards') as HTMLElement;
    const mobileLink = mobileCards.querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(mobileLink).not.toBeNull();
    expect(mobileLink.getAttribute('href')).toBe(expectedHref);
    expect(mobileLink.tabIndex).toBe(-1);
    expect(mobileLink).not.toBeVisible();
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

    const noteField = screen.getByRole('textbox', {name: 'Note'});
    expect(noteField).toHaveAttribute('aria-readonly', 'true');
    fireEvent.click(screen.getByRole('button', {name: /edit note/i}));
    expect(noteField).toHaveAttribute('aria-readonly', 'false');
    setRichTextEditorHtml(noteField, 'Updated note');
    fireEvent.click(screen.getByRole('button', {name: /save note/i}));

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([baseRow], 'Original Name', 'Updated note');
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
      expect(onUpdateShare).toHaveBeenCalledWith([baseRow], 'Updated Name', 'Owner note');
    });
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
      expect(onUpdateShare).toHaveBeenCalledWith([addedRow], 'Original Name', 'Owner note');
    });
    expect(await screen.findByText('Project removed.')).toBeInTheDocument();
  });

  it('expands all rows by default in shared mode so project details are visible', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} sharedMode note="See below" />);
    expect(within(desktopTable(container)).getByText(/A detailed project abstract\./)).toBeInTheDocument();
  });
});
