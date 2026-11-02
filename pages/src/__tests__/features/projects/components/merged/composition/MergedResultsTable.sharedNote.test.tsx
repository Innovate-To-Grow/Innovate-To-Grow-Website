import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/merged/composition/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
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

const normalizedBaseRow: ProjectGridRow = {...baseRow, semester_label: '2025 Spring'};

const rowWithId: ProjectGridRow = {
  ...baseRow,
  id: '11111111-1111-4111-8111-111111111111',
};

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

const setRichTextEditorHtml = (editor: HTMLElement, html: string) => {
  editor.innerHTML = html;
  fireEvent.input(editor);
};

// The shared page's curation note: one read view for its owner and visitors, and the owner's editor in its place.
describe('MergedResultsTable in shared mode: the curation note', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('marks the note\'s links to other sites as member content for visitors', () => {
    const {container} = render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        note={`<p>See <a href="https://elsewhere.example.com/x">this</a> and <a href="/past-projects">ours</a></p>`}
      />,
    );

    const links = container.querySelectorAll('.project-grid-shared-note a');
    expect([...links].map((link) => [link.textContent, link.getAttribute('rel')])).toEqual([
      ['this', 'nofollow ugc noopener'],
      ['ours', null],
    ]);
  });

  it('does not render a note block in shared mode when note is empty', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} sharedMode note="" />);
    expect(container.querySelector('.project-grid-shared-note')).toBeNull();
    expect(screen.queryByText('Curation note')).toBeNull();
    expect(screen.queryByText('No curation note yet.')).toBeNull();
  });

  it("shows its owner the note as visitors read it, with Edit Curation Note on the label's row", async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);
    const {container, rerender} = render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Shared"
        note="<p>Owner highlights</p>"
        onUpdateShare={onUpdateShare}
      />,
    );

    const note = container.querySelector('.project-grid-shared-note') as HTMLElement;
    const header = note.querySelector('.project-grid-shared-note-header') as HTMLElement;
    expect(within(header).getByText('Curation note')).toHaveClass('project-grid-shared-note-label');
    expect(within(header).getByRole('button', {name: 'Edit Curation Note'})).toBeInTheDocument();
    expect(within(note).getByText('Owner highlights')).toBeInTheDocument();
    expect(container.querySelector('[contenteditable]')).toBeNull();

    // Editing replaces the read view with the editor; saving brings the read view back, focus on Edit.
    fireEvent.click(within(header).getByRole('button', {name: 'Edit Curation Note'}));
    expect(container.querySelector('.project-grid-shared-note')).toBeNull();
    const noteField = screen.getByRole('textbox', {name: 'Curation note'});
    setRichTextEditorHtml(noteField, '<p>Owner picks</p>');
    fireEvent.click(screen.getByRole('button', {name: 'Save Curation Note'}));
    await waitFor(() => expect(onUpdateShare).toHaveBeenCalledWith([normalizedBaseRow], 'Shared', '<p>Owner picks</p>'));
    // The page stores the saved note and passes it back down, as the shared page's mutations do.
    rerender(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Shared"
        note="<p>Owner picks</p>"
        onUpdateShare={onUpdateShare}
      />,
    );

    await waitFor(() => expect(screen.queryByRole('textbox', {name: 'Curation note'})).toBeNull());
    expect(within(container.querySelector('.project-grid-shared-note') as HTMLElement).getByText('Owner picks')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Edit Curation Note'})).toHaveFocus();
  });

  it('tells its owner, and only its owner, that a curation has no note yet', () => {
    const {container, unmount} = render(
      <MergedResultsTable
        rows={makeItems()}
        sharedMode
        editable
        title="Shared"
        note=""
        onUpdateShare={vi.fn()}
      />,
    );

    const note = container.querySelector('.project-grid-shared-note') as HTMLElement;
    expect(note).toHaveClass('is-empty');
    expect(within(note).getByText('Curation note')).toBeInTheDocument();
    expect(within(note).getByText('No curation note yet.')).toHaveClass('project-grid-shared-note-empty');
    expect(within(note).getByRole('button', {name: 'Edit Curation Note'})).toBeInTheDocument();
    unmount();

    render(<MergedResultsTable rows={makeItems()} sharedMode title="Shared" note="" />);
    expect(screen.queryByText('No curation note yet.')).toBeNull();
    expect(screen.queryByText('Curation note')).toBeNull();
    expect(screen.queryByRole('button', {name: 'Edit Curation Note'})).toBeNull();
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

    // The saved note reads as text until Edit Curation Note opens the editor in its place.
    expect(screen.queryByRole('textbox', {name: 'Curation note'})).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Edit Curation Note'}));
    const noteField = screen.getByRole('textbox', {name: 'Curation note'});
    expect(noteField).toHaveAttribute('aria-readonly', 'false');
    expect(noteField).toHaveFocus();
    setRichTextEditorHtml(noteField, 'Updated note');
    fireEvent.click(screen.getByRole('button', {name: 'Save Curation Note'}));

    await waitFor(() => {
      expect(onUpdateShare).toHaveBeenCalledWith([normalizedBaseRow], 'Original Name', 'Updated note');
    });
    expect(onUpdateShare.mock.calls[0]).toHaveLength(3);
    expect(await screen.findByText('Note updated.')).toBeInTheDocument();
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
    const insertButton = screen.getByRole('button', {name: 'Insert Projects into Note'});
    insertButton.focus();
    fireEvent.click(insertButton);

    await waitFor(() => expect(noteEditor.textContent).toContain('Project 1'));
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
    expect(screen.queryByRole('textbox', {name: 'Curation note'})).toBeNull();
    expect(screen.getByRole('button', {name: 'Edit Curation Note'})).toHaveFocus();
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

    await waitFor(() => expect(screen.queryByRole('textbox', {name: 'Curation note'})).toBeNull());
    expect(screen.getByText('second')).toBeInTheDocument();
  });
});
