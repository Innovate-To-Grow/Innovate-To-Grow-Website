import {cleanup, fireEvent, render, screen} from '@testing-library/react';
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

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

describe('MergedResultsTable', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
  });

  afterEach(() => {
    cleanup();
  });

  it('submits the typed note when an authenticated user creates a share', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    const textarea = screen.getByLabelText(/add a note/i);
    fireEvent.change(textarea, {target: {value: 'Review these with the team'}});
    fireEvent.click(screen.getByRole('button', {name: /get shareable url/i}));

    expect(onCreateShare).toHaveBeenCalledTimes(1);
    const [rowsArg, noteArg] = onCreateShare.mock.calls[0];
    expect(noteArg).toBe('Review these with the team');
    expect(rowsArg[0]).toMatchObject({project_title: 'Shared Project'});
    openSpy.mockRestore();
  });

  it('hides the share controls and shows a login hint for anonymous users', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});
    const onCreateShare = vi.fn();

    render(<MergedResultsTable rows={makeItems()} onCreateShare={onCreateShare} />);

    expect(screen.queryByRole('button', {name: /get shareable url/i})).toBeNull();
    expect(screen.queryByLabelText(/add a note/i)).toBeNull();
    expect(screen.getByText(/to create a shareable link/i)).toBeInTheDocument();
  });

  it('renders the note above the table in shared mode', () => {
    const {container} = render(
      <MergedResultsTable rows={makeItems()} sharedMode note="Curated highlights" />,
    );

    const noteBlock = container.querySelector('.project-grid-shared-note');
    expect(noteBlock).not.toBeNull();
    expect(screen.getByText('Curated highlights')).toBeInTheDocument();
    // No create controls in shared mode.
    expect(screen.queryByRole('button', {name: /get shareable url/i})).toBeNull();
    expect(screen.queryByLabelText(/add a note/i)).toBeNull();
  });

  it('does not render a note block in shared mode when note is empty', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} sharedMode note="" />);
    expect(container.querySelector('.project-grid-shared-note')).toBeNull();
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
