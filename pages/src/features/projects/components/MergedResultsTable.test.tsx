import {useState} from 'react';
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

const filteredShareRow: ProjectGridRow = {
  ...addedRow,
  project_title: 'Shared Project Beta',
};

const unsharedLocalRow: ProjectGridRow = {
  ...addedRow,
  team_number: 'T03',
  project_title: 'Local Only Project',
};

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

describe('MergedResultsTable', () => {
  let originalClipboard: Clipboard | undefined;

  beforeEach(() => {
    originalClipboard = navigator.clipboard;
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
  });

  it('submits the name + note when an authenticated user creates a share', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => {
      throw new Error('Past projects should show share links in the page instead of opening a browser popup.');
    });

    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'Spring finalists'}});
    fireEvent.change(screen.getByLabelText(/add a note/i), {target: {value: 'Review these with the team'}});
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    expect(onCreateShare).toHaveBeenCalledTimes(1);
    const [rowsArg, nameArg, noteArg] = onCreateShare.mock.calls[0];
    expect(nameArg).toBe('Spring finalists');
    expect(noteArg).toBe('Review these with the team');
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    expect(await screen.findByDisplayValue('https://example.test/past-projects/abc')).toBeInTheDocument();
    expect(screen.queryByText(/the link is ready/i)).toBeNull();
    expect(screen.queryByRole('link', {name: /open shared page/i})).toBeNull();
    expect(screen.queryByRole('button', {name: /copy url/i})).toBeNull();
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('copies the share URL when the URL field is clicked', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {writeText},
    });

    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'Spring finalists'}});
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    const shareUrlInput = await screen.findByLabelText('Shareable URL');
    fireEvent.click(shareUrlInput);

    expect(writeText).toHaveBeenCalledWith('https://example.test/past-projects/abc');
    expect(await screen.findByText('URL copied to clipboard.')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /copy url/i})).toBeNull();
  });

  it('updates the created share when a row is removed after creating a shareable URL', async () => {
    const onCreateShare = vi.fn().mockResolvedValue({id: 'share-abc', share_url: '/past-projects/share-abc'});
    const onUpdateCreatedShare = vi.fn().mockResolvedValue(undefined);

    const StatefulMergedResults = () => {
      const [items, setItems] = useState(() => makeItems([baseRow, addedRow]));

      return (
        <MergedResultsTable
          rows={items}
          onCreateShare={onCreateShare}
          onUpdateCreatedShare={onUpdateCreatedShare}
          onDeleteRow={(row) => {
            setItems((current) => current.filter((item) => item.__key !== row.__key));
          }}
        />
      );
    };

    render(<StatefulMergedResults />);

    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'Spring finalists'}});
    fireEvent.change(screen.getByLabelText(/add a note/i), {target: {value: 'Review these with the team'}});
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    expect(await screen.findByLabelText('Shareable URL')).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', {name: /remove/i})[0]);

    await waitFor(() => {
      expect(onUpdateCreatedShare).toHaveBeenCalledWith(
        'share-abc',
        [addedRow],
        'Spring finalists',
        'Review these with the team',
      );
    });
    expect(await screen.findByText('Project removed from the shareable link.')).toBeInTheDocument();
    expect(screen.queryByText('Shared Project')).toBeNull();
    expect(screen.getAllByText('Irrigation Sensor').length).toBeGreaterThan(0);
  });

  it('does not write unshared local rows back into a filtered share when removing a row', async () => {
    const onCreateShare = vi.fn().mockResolvedValue({id: 'share-filtered'});
    const onUpdateCreatedShare = vi.fn().mockResolvedValue(undefined);

    const StatefulMergedResults = () => {
      const [items, setItems] = useState(() => makeItems([baseRow, filteredShareRow, unsharedLocalRow]));

      return (
        <MergedResultsTable
          rows={items}
          onCreateShare={onCreateShare}
          onUpdateCreatedShare={onUpdateCreatedShare}
          onDeleteRow={(row) => {
            setItems((current) => current.filter((item) => item.__key !== row.__key));
          }}
        />
      );
    };

    render(<StatefulMergedResults />);

    fireEvent.change(screen.getByPlaceholderText('Search projects...'), {target: {value: 'Shared Project'}});
    fireEvent.change(screen.getByLabelText(/name this shared link/i), {target: {value: 'Filtered finalists'}});
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    expect(await screen.findByLabelText('Shareable URL')).toBeInTheDocument();
    expect(onCreateShare).toHaveBeenCalledWith([baseRow, filteredShareRow], 'Filtered finalists', '');

    fireEvent.click(screen.getAllByRole('button', {name: /remove/i})[0]);

    await waitFor(() => {
      expect(onUpdateCreatedShare).toHaveBeenCalledWith('share-filtered', [filteredShareRow], 'Filtered finalists', '');
    });
  });

  it('keeps the share button disabled until a name is entered', () => {
    const onCreateShare = vi.fn();
    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    const button = screen.getByRole('button', {name: /get shareable url/i});
    expect(button).toBeDisabled();

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

    // No create controls in shared mode.
    expect(screen.queryByRole('button', {name: /get shareable url/i})).toBeNull();
    expect(screen.queryByRole('button', {name: /copy url/i})).toBeNull();
    expect(screen.queryByLabelText(/add a note/i)).toBeNull();
    expect(screen.queryByLabelText('Add Project')).toBeNull();
    expect(screen.queryByRole('button', {name: /save note/i})).toBeNull();
    expect(screen.queryAllByRole('button', {name: /remove/i})).toHaveLength(0);
    const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]');
    expect(exportCluster).not.toBeNull();
    expect(within(exportCluster as HTMLElement).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'PDF',
      'Microsoft Word',
      'Excel',
    ]);
    expect(screen.queryByRole('button', {name: 'CSV'})).toBeNull();

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
      expect(onUpdateShare).toHaveBeenCalledWith([baseRow], 'Updated note', 'Original Name');
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
        onUpdateShare={onUpdateShare}
      />,
    );

    expect(screen.getByRole('heading', {name: 'Original Name'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /edit name/i}));
    const nameField = screen.getByLabelText('Shared page name');
    fireEvent.change(nameField, {target: {value: 'Updated Name'}});
    fireEvent.click(screen.getByRole('button', {name: /save name/i}));

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([baseRow], 'Owner note', 'Updated Name');
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
      expect(onUpdateShare).toHaveBeenCalledWith([addedRow], 'Owner note', 'Original Name');
    });
    expect(await screen.findByText('Project removed.')).toBeInTheDocument();
  });

  it('expands all detail rows by default in shared mode', () => {
    render(<MergedResultsTable rows={makeItems()} sharedMode note="See below" />);
    // Abstract + student names are only in the DOM when a row is expanded.
    expect(screen.getAllByText(/A detailed project abstract\./).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Alice, Bob/).length).toBeGreaterThan(0);
  });

  it('does not expand detail rows by default in builder mode', () => {
    render(<MergedResultsTable rows={makeItems()} onCreateShare={vi.fn()} />);
    // Not shared → rows start collapsed, so the abstract text is absent.
    expect(screen.queryByText(/A detailed project abstract\./)).toBeNull();
  });
});
