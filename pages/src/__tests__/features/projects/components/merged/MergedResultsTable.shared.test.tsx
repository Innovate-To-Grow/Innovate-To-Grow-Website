
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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

  it('heads a shared list search with no matches one level under the list title (h2)', () => {
    render(<MergedResultsTable rows={makeItems([baseRow, addedRow])} sharedMode title="Spring picks" />);

    fireEvent.change(screen.getByRole('searchbox', {name: 'Search this list'}), {target: {value: 'hydroponics'}});

    expect(screen.getByRole('heading', {level: 1, name: 'Spring picks'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 2, name: 'No projects match “hydroponics”'})).toBeInTheDocument();
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
