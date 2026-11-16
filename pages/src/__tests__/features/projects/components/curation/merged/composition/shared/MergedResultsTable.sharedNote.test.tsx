import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/curation/merged/composition/MergedResultsTable';
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
});
