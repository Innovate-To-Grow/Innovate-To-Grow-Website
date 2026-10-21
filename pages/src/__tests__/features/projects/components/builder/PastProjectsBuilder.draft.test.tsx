import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/projectGrid';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockBuildLoginPath = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();
const authenticatedAuth = {
  isAuthenticated: true,
  isInitializing: false,
  unverified: false,
  user: {member_uuid: 'member-1', email: 'member@example.com'},
};

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/auth/api/redirects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth/api/redirects')>();
  return {
    ...actual,
    buildLoginPath: (...args: unknown[]) => mockBuildLoginPath(...args),
  };
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    searchPastProjectsWithAI: (...args: unknown[]) => mockSearchPastProjectsWithAI(...args),
    hydrateProjectGridRowsSettled: (...args: unknown[]) => mockHydrateProjectGridRowsSettled(...args),
  };
});

const makeRow = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: 'T01',
  team_name: 'Team Alpha',
  project_title: 'Alpha Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: '',
  student_names: '',
  is_presenting: '',
  ...overrides,
});

const ROWS: ProjectGridRow[] = [
  makeRow({team_number: 'T01', team_name: 'Team Alpha', project_title: 'Alpha Project'}),
  makeRow({team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'}),
  makeRow({team_number: 'T03', team_name: 'Team Charlie', project_title: 'Charlie Project'}),
];

const getMergedSection = () => {
  const heading = screen.queryByRole('heading', {name: /saved merged results/i});
  return heading ? (heading.closest('section') as HTMLElement) : null;
};

describe('PastProjectsBuilder — the kept draft', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue(authenticatedAuth);
    mockSearchPastProjectsWithAI.mockReset();
    mockBuildLoginPath.mockReset();
    mockHydrateProjectGridRowsSettled.mockReset();
    // The builder keeps its draft in localStorage; clear it so drafts don't leak between tests.
    localStorage.clear();
    sessionStorage.clear();
    vi.spyOn(window, 'confirm').mockImplementation(() => {
      throw new Error('Past projects should use an in-page confirmation dialog.');
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // The draft (saved projects, name and note) is kept in localStorage: the login button reloads the page, and a
  // visitor who closes the tab must find the curation they were building when they come back.
  const DRAFT_STORAGE_KEY = 'past-projects:builder:draft';
  const LEGACY_MERGED_ROWS_STORAGE_KEY = 'past-projects:builder:merged-rows';
  const storeDraft = (rows: ProjectGridRow[], extra: {owner?: string | null; name?: string; note?: string} = {}) =>
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({owner: null, rows, name: '', note: '', ...extra}));
  const storedDraft = () => {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as {owner: string | null; rows: ProjectGridRow[]; name: string; note: string}) : null;
  };

  it('restores the draft kept from an earlier visit, with its name and note', () => {
    storeDraft([makeRow({team_number: 'T09', project_title: 'Persisted Project'})], {
      owner: 'member-1',
      name: 'Water picks',
      note: 'For the board',
    });

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const merged = getMergedSection();
    expect(merged).not.toBeNull();
    expect(within(merged as HTMLElement).getAllByText('Persisted Project').length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/curation name/i)).toHaveValue('Water picks');
    expect(screen.getByRole('textbox', {name: /curation note/i})).toHaveTextContent('For the board');
  });

  it('keeps the draft in localStorage, owned by the member, so closing the tab does not lose it', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(storedDraft()).toBeNull();

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'My picks'}});
    const note = screen.getByRole('textbox', {name: /curation note/i});
    note.innerHTML = 'Why these';
    fireEvent.input(note);

    const draft = storedDraft();
    expect(draft?.owner).toBe('member-1');
    expect(draft?.rows.map((row) => row.project_title)).toEqual(['Bravo Project']);
    expect(draft?.name).toBe('My picks');
    expect(draft?.note).toBe('Why these');
  });

  it("does not restore another member's draft and drops it", () => {
    storeDraft([makeRow({team_number: 'T09', project_title: 'Persisted Project'})], {owner: 'member-2'});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(getMergedSection()).toBeNull();
    expect(storedDraft()).toBeNull();
  });

  it('picks up projects kept in sessionStorage by the earlier version, once', () => {
    sessionStorage.setItem(
      LEGACY_MERGED_ROWS_STORAGE_KEY,
      JSON.stringify([makeRow({team_number: 'T09', project_title: 'Persisted Project'})]),
    );

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(within(getMergedSection() as HTMLElement).getAllByText('Persisted Project').length).toBeGreaterThan(0);
    expect(sessionStorage.getItem(LEGACY_MERGED_ROWS_STORAGE_KEY)).toBeNull();
    expect(storedDraft()?.rows.map((row) => row.project_title)).toEqual(['Persisted Project']);
  });

  it('clears the kept draft once the curation is saved', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    expect(storedDraft()).not.toBeNull();

    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'My picks'}});
    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    expect(onCreateShare.mock.calls[0][1]).toBe('My picks');
    await waitFor(() => expect(storedDraft()).toBeNull());
  });

  it('keeps the draft when saving the curation fails', async () => {
    // The whole point of persistence is to not lose the user's merged rows; a failed save
    // (network error, 4xx/5xx) must leave the draft intact so they can retry.
    const onCreateShare = vi.fn().mockRejectedValue(new Error('boom'));
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    expect(storedDraft()).not.toBeNull();

    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'My picks'}});
    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    // Draft retained after the rejection — the clear runs only after a successful await.
    expect(storedDraft()?.name).toBe('My picks');
  });

  it('drops the draft when the user logs out in the same tab', () => {
    // Without this the next person on a shared computer would get the first member's curation.
    mockUseAuth.mockReturnValue(authenticatedAuth);
    storeDraft([makeRow({team_number: 'T09', project_title: 'Persisted Project'})], {owner: 'member-1'});

    const {rerender} = render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    expect(getMergedSection()).not.toBeNull();

    mockUseAuth.mockReturnValue({isAuthenticated: false});
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(storedDraft()).toBeNull();
    expect(getMergedSection()).toBeNull();
  });

  it('keeps the draft through revalidation and a temporary verification failure', () => {
    const builder = <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />;
    const {rerender} = render(builder);
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    const draft = localStorage.getItem(DRAFT_STORAGE_KEY);

    for (const isInitializing of [true, false]) {
      mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, unverified: true, isInitializing});
      rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      expect(localStorage.getItem(DRAFT_STORAGE_KEY)).toBe(draft);
      expect(within(getMergedSection() as HTMLElement).getAllByText('Bravo Project').length).toBeGreaterThan(0);
    }

    mockUseAuth.mockReturnValue(authenticatedAuth);
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(localStorage.getItem(DRAFT_STORAGE_KEY)).toBe(draft);
  });

  it('keeps a guest draft when the guest signs in', () => {
    mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, user: null});
    storeDraft([ROWS[1]]);
    const {rerender} = render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    const draft = localStorage.getItem(DRAFT_STORAGE_KEY);
    expect(draft).not.toBeNull();
    mockUseAuth.mockReturnValue(authenticatedAuth);
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(localStorage.getItem(DRAFT_STORAGE_KEY)).toBe(draft);
    expect(getMergedSection()).not.toBeNull();
  });

  it('clears the draft when switching directly to another member', () => {
    storeDraft([ROWS[1]], {owner: 'member-1', note: 'Private note'});
    const {rerender} = render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    mockUseAuth.mockReturnValue({...authenticatedAuth, user: {...authenticatedAuth.user, member_uuid: 'member-2'}});
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(storedDraft()).toBeNull();
    expect(getMergedSection()).toBeNull();
  });

  it('clears a restored member draft when initial session verification confirms logout', () => {
    mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, isInitializing: true, unverified: true});
    storeDraft([ROWS[1]], {owner: 'member-1'});
    const {rerender} = render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    expect(getMergedSection()).not.toBeNull();
    mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, user: null});
    rerender(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    expect(storedDraft()).toBeNull();
    expect(getMergedSection()).toBeNull();
  });

  it('does not restore an in-flight merge after a confirmed logout', async () => {
    let resolveDetails!: (result: {rows: ProjectGridRow[]; failedIndexes: number[]; unavailableIndexes: number[]}) => void;
    mockHydrateProjectGridRowsSettled.mockReturnValue(
      new Promise((resolve) => { resolveDetails = resolve; }),
    );
    const rows = [makeRow({id: 'pending-project'})];
    const {rerender} = render(
      <PastProjectsBuilder rows={rows} loading={false} error={null} onCreateShare={vi.fn()} />,
    );
    fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save selected/i}));
    expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalledTimes(1);
    mockUseAuth.mockReturnValue({...authenticatedAuth, isAuthenticated: false, user: null});
    rerender(<PastProjectsBuilder rows={rows} loading={false} error={null} onCreateShare={vi.fn()} />);
    await act(async () => resolveDetails({rows: [{...rows[0], abstract: 'Loaded details'}], failedIndexes: [], unavailableIndexes: []}));
    expect(storedDraft()).toBeNull();
    expect(getMergedSection()).toBeNull();
    // The dropped save says so where it was started, and keeps the checkbox for a retry.
    expect(screen.getByRole('alert')).toHaveTextContent('Your sign-in changed while saving, so nothing was saved.');
    expect(screen.getAllByLabelText('Select Alpha Project')[0]).toBeChecked();
  });

  it('ignores a malformed kept draft', () => {
    localStorage.setItem(DRAFT_STORAGE_KEY, '{not valid json');

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(getMergedSection()).toBeNull();
  });
});
