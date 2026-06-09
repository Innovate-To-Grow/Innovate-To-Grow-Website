import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/MergedResultsTable';
import {createPastProjectsDetailText} from '@/features/projects/components/pastProjectsDetailText';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/projectGrid';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

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

const setRichEditorHtml = (editor: HTMLElement, html: string) => {
  editor.innerHTML = html;
  fireEvent.input(editor);
};

const selectNodeContents = (node: Node) => {
  const range = document.createRange();
  range.selectNodeContents(node);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
};

const getExportButtonLabels = (container: HTMLElement) => {
  const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]');
  expect(exportCluster).not.toBeNull();
  return within(exportCluster as HTMLElement).getAllByRole('button').map((button) => button.textContent);
};

describe('MergedResultsTable', () => {
  let originalClipboard: Clipboard | undefined;
  let originalClipboardItem: typeof ClipboardItem | undefined;

  beforeEach(() => {
    originalClipboard = navigator.clipboard;
    originalClipboardItem = window.ClipboardItem;
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: originalClipboard,
    });
    if (originalClipboardItem) {
      Object.defineProperty(window, 'ClipboardItem', {
        configurable: true,
        value: originalClipboardItem,
      });
    } else {
      Reflect.deleteProperty(window, 'ClipboardItem');
    }
  });

  it('separates multiple generated project detail blocks with a visible divider', () => {
    expect(createPastProjectsDetailText([baseRow, addedRow])).toContain(
      'Abstract: A detailed project abstract.\n\n------------------------------\n\nProject 2',
    );
  });

  it('submits the name, note, and details text when an authenticated user creates a share', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => {
      throw new Error('Past projects should show share links in the page instead of opening a browser popup.');
    });

    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    const detailsField = screen.getByRole('textbox', {name: 'Past Projects Detail'});
    expect(detailsField).toHaveTextContent(/Abstract: A detailed project abstract\./);
    expect(detailsField).toHaveTextContent(/Students: Alice, Bob/);
    expect(screen.getByRole('button', {name: 'Bold'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Highlight'})).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'Spring finalists'}});
    fireEvent.change(screen.getByLabelText(/add a note/i), {target: {value: 'Review these with the team'}});
    setRichEditorHtml(detailsField, '<strong>Custom</strong> <mark>project</mark> details');
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    expect(onCreateShare).toHaveBeenCalledTimes(1);
    const [rowsArg, nameArg, noteArg, detailsArg] = onCreateShare.mock.calls[0];
    expect(nameArg).toBe('Spring finalists');
    expect(noteArg).toBe('Review these with the team');
    expect(detailsArg).toBe('<strong>Custom</strong> <mark>project</mark> details');
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(await screen.findByText('Opening shareable link...')).toBeInTheDocument();
    expect(screen.queryByLabelText('Shareable URL')).toBeNull();
    expect(screen.queryByRole('link', {name: /open shared page/i})).toBeNull();
    expect(screen.queryByRole('button', {name: /copy url/i})).toBeNull();
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('copies all project detail with rich HTML and plain text clipboard payloads', async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    class MockClipboardItem {
      items: Record<string, Blob>;

      constructor(items: Record<string, Blob>) {
        this.items = items;
      }
    }

    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {write},
    });
    Object.defineProperty(window, 'ClipboardItem', {
      configurable: true,
      value: MockClipboardItem,
    });

    render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);

    const detailsField = screen.getByRole('textbox', {name: 'Past Projects Detail'});
    setRichEditorHtml(detailsField, '<strong>Copied</strong> <mark>highlight</mark><br>Plain');
    fireEvent.click(screen.getByRole('button', {name: 'Copy All'}));

    await waitFor(() => {
      expect(write).toHaveBeenCalledTimes(1);
    });
    const item = write.mock.calls[0][0][0] as MockClipboardItem;
    await expect(item.items['text/html'].text()).resolves.toContain('<strong>Copied</strong>');
    await expect(item.items['text/html'].text()).resolves.toContain(
      '<mark style="background-color:#fff3a3;color:inherit;">highlight</mark>',
    );
    await expect(item.items['text/plain'].text()).resolves.toBe('Copied highlight\nPlain');
    expect(await screen.findByText('Past Projects Detail copied.')).toBeInTheDocument();
  });

  it('clears selected rich formatting from the project detail editor', () => {
    render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);

    const detailsField = screen.getByRole('textbox', {name: 'Past Projects Detail'});
    setRichEditorHtml(detailsField, '<strong>Bold</strong> <mark>Highlighted</mark> <em>Italic</em>');

    const highlightedText = detailsField.querySelector('mark');
    expect(highlightedText).not.toBeNull();
    selectNodeContents(highlightedText as Node);
    fireEvent.click(screen.getByRole('button', {name: 'Clear formatting'}));

    expect(detailsField).toHaveTextContent('Bold Highlighted Italic');
    expect(detailsField.querySelector('mark')).toBeNull();
    expect(detailsField.querySelector('strong')?.textContent).toBe('Bold');
    expect(detailsField.querySelector('em')?.textContent).toBe('Italic');
  });

  it('toggles selected highlight formatting off from the project detail editor', () => {
    render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);

    const detailsField = screen.getByRole('textbox', {name: 'Past Projects Detail'});
    setRichEditorHtml(detailsField, '<strong>Bold</strong> <mark>Highlighted</mark> <em>Italic</em>');

    const highlightedText = detailsField.querySelector('mark');
    expect(highlightedText).not.toBeNull();
    selectNodeContents(highlightedText as Node);
    fireEvent.click(screen.getByRole('button', {name: 'Highlight'}));

    expect(detailsField).toHaveTextContent('Bold Highlighted Italic');
    expect(detailsField.querySelector('mark')).toBeNull();
    expect(detailsField.querySelector('strong')?.textContent).toBe('Bold');
    expect(detailsField.querySelector('em')?.textContent).toBe('Italic');
  });

  it('bounds large all-project detail sets without truncating the submitted detail text', async () => {
    const largeRows = Array.from({length: 25}, (_, index) => ({
      ...baseRow,
      team_number: `T${String(index + 1).padStart(2, '0')}`,
      team_name: `Team ${index + 1}`,
      project_title: `Project Title ${index + 1}`,
      abstract: `Abstract ${index + 1}`,
      student_names: `Student ${index + 1}`,
    }));
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/large');

    render(<MergedResultsTable rows={makeItems(largeRows)} onCreateShare={onCreateShare} />);

    const detailsField = screen.getByRole('textbox', {name: 'Past Projects Detail'});
    expect(detailsField).toHaveClass('is-large-detail-set');
    expect(detailsField.closest('.project-grid-rich-detail-editor')).toHaveAttribute('data-project-count', '25');
    expect(detailsField).toHaveTextContent('Project 25');
    expect(detailsField).toHaveTextContent('Abstract: Abstract 25');

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'All selected projects'}});
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    await waitFor(() => {
      expect(onCreateShare).toHaveBeenCalledTimes(1);
    });
    const detailsArg = onCreateShare.mock.calls[0][3] as string;
    expect(detailsArg).toContain('Project 25');
    expect(detailsArg).toContain('Abstract: Abstract 25');
    expect(detailsArg.match(/------------------------------/g)).toHaveLength(24);
  });

  it('copies the share URL when the URL field is clicked', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {writeText},
    });

    render(<MergedResultsTable rows={makeItems()} sharedMode />);

    const shareUrlInput = await screen.findByLabelText('Shareable URL');
    fireEvent.click(shareUrlInput);

    expect(writeText).toHaveBeenCalledWith(window.location.href);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('URL copied to clipboard.')).toBeNull();
    expect(screen.queryByRole('button', {name: /copy url/i})).toBeNull();
  });

  it('keeps the share button disabled until a name is entered', () => {
    const onCreateShare = vi.fn();
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    const button = screen.getByRole('button', {name: /get shareable url/i});
    expect(button).toBeDisabled();
    expect(getExportButtonLabels(container)).toEqual(['CSV', 'Excel', 'PDF', 'Microsoft Word']);

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'Named'}});
    expect(button).toBeEnabled();
  });

  it('hides the share controls and shows a login hint for anonymous users', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});
    const onCreateShare = vi.fn();

    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    expect(screen.queryByRole('button', {name: /get shareable url/i})).toBeNull();
    expect(screen.queryByLabelText(/name this shared link/i)).toBeNull();
    expect(screen.queryByLabelText(/add a note/i)).toBeNull();
    expect(screen.getByText(/to create a shareable link/i)).toBeInTheDocument();
  });

  it('renders the share link above the note in shared mode', async () => {
    const {container} = render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        note="Curated highlights"
        detailsText="<strong>Saved</strong> <mark>project</mark> details"
      />,
    );

    const shareBlock = await screen.findByRole('status');
    const noteBlock = container.querySelector('.project-grid-shared-note');
    const detailsBlock = container.querySelector('.project-grid-shared-detail');
    expect(noteBlock).not.toBeNull();
    expect(detailsBlock).not.toBeNull();
    expect(screen.getByText('Curated highlights')).toBeInTheDocument();
    await waitFor(() => {
      expect(detailsBlock?.querySelector('strong')?.textContent).toBe('Saved');
      expect(detailsBlock?.querySelector('mark')?.textContent).toBe('project');
    });
    expect(within(detailsBlock as HTMLElement).getByRole('button', {name: 'Copy All'})).toBeInTheDocument();
    expect(screen.getByLabelText('Shareable URL')).toBeInTheDocument();

    const headerBlocks = Array.from(
      container.querySelectorAll('.project-grid-share-result, .project-grid-shared-note, .project-grid-shared-detail'),
    );
    expect(headerBlocks[0]).toBe(shareBlock);
    expect(headerBlocks[1]).toBe(noteBlock);
    expect(headerBlocks[2]).toBe(detailsBlock);

    // No create controls in shared mode.
    expect(screen.queryByRole('button', {name: /get shareable url/i})).toBeNull();
    expect(screen.queryByRole('button', {name: /copy url/i})).toBeNull();
    expect(screen.queryByLabelText(/add a note/i)).toBeNull();
    expect(screen.queryByLabelText('Add Project')).toBeNull();
    expect(screen.queryByRole('button', {name: /save note/i})).toBeNull();
    expect(screen.queryAllByRole('button', {name: /remove/i})).toHaveLength(0);
    expect(getExportButtonLabels(container)).toEqual(['CSV', 'Excel', 'PDF', 'Microsoft Word']);

    const tableShell = container.querySelector('.project-grid-table-shell');
    const toolbar = container.querySelector('.project-grid-toolbar');
    expect(toolbar).toHaveClass('project-grid-toolbar--bottom');
    expect(tableShell?.lastElementChild).toBe(toolbar);
  });

  it('does not render a note block in shared mode when note is empty', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} sharedMode note="" />);
    expect(container.querySelector('.project-grid-shared-note')).toBeNull();
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
        detailsText="Original details"
        onUpdateShare={onUpdateShare}
      />,
    );

    const noteField = screen.getByLabelText('Note');
    expect(noteField).toHaveAttribute('readonly');
    fireEvent.click(screen.getByRole('button', {name: /edit note/i}));
    expect(noteField).not.toHaveAttribute('readonly');
    fireEvent.change(noteField, {target: {value: 'Updated note'}});
    fireEvent.click(screen.getByRole('button', {name: /save note/i}));

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([baseRow], 'Updated note', 'Original Name', 'Original details');
    });
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
        detailsText="Owner details"
        onUpdateShare={onUpdateShare}
      />,
    );

    expect(screen.getByRole('heading', {name: 'Original Name'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /edit name/i}));
    const nameField = screen.getByLabelText('Shared page name');
    fireEvent.change(nameField, {target: {value: 'Updated Name'}});
    fireEvent.click(screen.getByRole('button', {name: /save name/i}));

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([baseRow], 'Owner note', 'Updated Name', 'Owner details');
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
        detailsText="Owner details"
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getAllByRole('button', {name: /remove/i})[0]);

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([addedRow], 'Owner note', 'Original Name', 'Owner details');
    });
    expect(await screen.findByText('Project removed.')).toBeInTheDocument();
  });

  it('lets an editable shared page save details text changes', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);

    render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Original Name"
        note="Owner note"
        detailsText="Original project details"
        onUpdateShare={onUpdateShare}
      />,
    );

    const detailsField = screen.getByRole('textbox', {name: 'Past Projects Detail'});
    expect(detailsField).toHaveAttribute('aria-readonly', 'true');
    fireEvent.click(screen.getByRole('button', {name: /edit past projects detail/i}));
    expect(detailsField).toHaveAttribute('aria-readonly', 'false');
    setRichEditorHtml(detailsField, '<strong>Updated</strong> project details');
    fireEvent.click(screen.getByRole('button', {name: /save past projects detail/i}));

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith(
        [baseRow],
        'Owner note',
        'Original Name',
        '<strong>Updated</strong> project details',
      );
    });
    expect(await screen.findByText('Past projects detail updated.')).toBeInTheDocument();
  });

  it('expands all detail rows by default in shared mode', () => {
    render(<MergedResultsTable rows={makeItems()} sharedMode note="See below" />);
    // Abstract + student names are only in the DOM when a row is expanded.
    expect(screen.getAllByText(/A detailed project abstract\./).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Alice, Bob/).length).toBeGreaterThan(0);
  });

  it('does not expand detail rows by default in builder mode', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    // Not shared -> table detail rows start collapsed, even though the generated
    // Past Projects Detail editor contains the same abstract text.
    expect(container.querySelector('.project-grid-detail-content')).toBeNull();
    expect(screen.getByRole('textbox', {name: 'Past Projects Detail'})).toHaveTextContent(
      /A detailed project abstract\./,
    );
  });
});
