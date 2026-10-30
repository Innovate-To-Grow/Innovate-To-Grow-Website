import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/merged/composition/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

// The API caps a curation's note at 50,000 characters (markup included). Inserting projects with their
// abstracts passes that at about thirty projects.
const LONG_ABSTRACT = 'An abstract that goes on. '.repeat(80);
const longRows = (count: number): ProjectGridRow[] =>
  Array.from({length: count}, (_, index) => ({
    id: `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
    semester_label: '2025-1 Spring',
    class_code: 'CAP',
    team_number: `T${index}`,
    team_name: `Team ${index}`,
    project_title: `Project ${index}`,
    organization: 'Acme',
    industry: 'Technology',
    abstract: LONG_ABSTRACT,
    student_names: 'Alice, Bob',
    is_presenting: '',
  }));
const TOO_LONG_NOTE = 'x'.repeat(50_001);

describe('MergedResultsTable — the curation note limit', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({isAuthenticated: true, user: {member_uuid: 'member-1'}});
  });

  afterEach(() => {
    cleanup();
  });

  it('refuses an insert that would make the note too long to save, and allows it without abstracts', async () => {
    const onUpdateShare = vi.fn().mockResolvedValue(undefined);
    render(
      <MergedResultsTable
        rows={createProjectGridItems(longRows(30), 'test')}
        sharedMode
        editable
        title="Shared"
        note=""
        onUpdateShare={onUpdateShare}
      />,
    );
    fireEvent.click(screen.getByRole('button', {name: /edit curation note/i}));
    const noteEditor = screen.getByRole('textbox', {name: 'Curation note'});
    const insertButton = screen.getByRole('button', {name: 'Insert projects into note'});
    insertButton.focus();

    fireEvent.click(insertButton);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Inserting 30 projects would make the note longer than a curation can save (50,000 characters with ' +
        'formatting). Leave out Abstract under Choose fields, or shorten the note.',
    );
    expect(noteEditor.textContent).toBe('');

    fireEvent.click(screen.getByRole('button', {name: 'Choose fields'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Abstract'}));
    expect(screen.queryByRole('alert')).toBeNull();
    insertButton.focus();
    fireEvent.click(insertButton);
    await waitFor(() => expect(noteEditor.textContent).toContain('Project 29'));
  });

  it('does not send a builder curation whose note is too long, and says why', () => {
    const onCreateShare = vi.fn();
    render(
      <MergedResultsTable
        rows={createProjectGridItems(longRows(1), 'test')}
        onCreateShare={onCreateShare}
        nameDraft=""
        noteDraft={TOO_LONG_NOTE}
        onNameDraftChange={vi.fn()}
        onNoteDraftChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getAllByRole('button', {name: 'Save Curation'})[0]);

    expect(onCreateShare).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent(
      'The curation note is too long to save: 50,001 characters with its formatting, and the limit is 50,000.',
    );
  });

  it("shows the API's reason when a curation page edit is refused", async () => {
    const onUpdateShare = vi.fn().mockRejectedValue({
      response: {status: 400, data: {note: ['Ensure this field has no more than 50000 characters.']}},
    });
    render(
      <MergedResultsTable
        rows={createProjectGridItems(longRows(1), 'test')}
        sharedMode
        editable
        title="Shared"
        note="Short note"
        onUpdateShare={onUpdateShare}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /edit name/i}));
    fireEvent.change(screen.getByLabelText('Curation name'), {target: {value: 'Renamed'}});
    fireEvent.click(screen.getByRole('button', {name: /save name/i}));

    expect(await screen.findByText('Ensure this field has no more than 50000 characters.')).toBeInTheDocument();
  });

  it('keeps a curation page note that is too long open for editing instead of sending it', () => {
    const onUpdateShare = vi.fn();
    render(
      <MergedResultsTable
        rows={createProjectGridItems(longRows(1), 'test')}
        sharedMode
        editable
        title="Shared"
        note=""
        onUpdateShare={onUpdateShare}
      />,
    );
    fireEvent.click(screen.getByRole('button', {name: /edit curation note/i}));
    const noteEditor = screen.getByRole('textbox', {name: 'Curation note'});
    noteEditor.innerHTML = TOO_LONG_NOTE;
    fireEvent.input(noteEditor);

    fireEvent.click(screen.getByRole('button', {name: /save curation note/i}));

    expect(onUpdateShare).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent('The curation note is too long to save');
    expect(screen.getByRole('button', {name: /save curation note/i})).toBeInTheDocument();
  });
});
