import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {authenticatedAuth, getMergedSection, makeRow, ROWS} from '@/__tests__/features/projects/components/builder/composition/fixtures/pastProjectsBuilderFixtures';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockBuildLoginPath = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/auth/api/navigation/redirects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth/api/navigation/redirects')>();
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

  it('opens with a malformed kept draft: rows missing fields are completed, anything else is dropped', () => {
    // Storage is not this page's to trust (an older version, an extension, a hand edit). A row without a
    // semester used to crash the page on every visit, since the draft was never cleared.
    localStorage.setItem(
      DRAFT_STORAGE_KEY,
      JSON.stringify({owner: null, rows: [{project_title: 'Half a row'}, null, 'text', 7, ['nested'], {}], name: 3}),
    );

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(screen.getByRole('heading', {level: 2, name: 'Search Tables'})).toBeInTheDocument();
    expect(within(getMergedSection() as HTMLElement).getAllByText('Half a row').length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/curation name/i)).toHaveValue('');
    expect(storedDraft()?.rows).toEqual([makeRow({
      semester_label: '', class_code: '', team_number: '', team_name: '', project_title: 'Half a row',
      organization: '', industry: '',
    })]);
  });

  it('drops malformed rows kept in sessionStorage by the earlier version', () => {
    sessionStorage.setItem(LEGACY_MERGED_ROWS_STORAGE_KEY, JSON.stringify([{team_name: 'Team Legacy'}, null, 5]));

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(within(getMergedSection() as HTMLElement).getAllByText('Team Legacy').length).toBeGreaterThan(0);
    expect(storedDraft()?.rows.map((row) => row.team_name)).toEqual(['Team Legacy']);
  });

  it('clears the kept draft once the curation is saved', async () => {
    const onCreateShare = vi.fn().mockResolvedValue('https://example.test/past-projects/abc');
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    expect(storedDraft()).not.toBeNull();

    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'My picks'}});
    fireEvent.click(screen.getAllByRole('button', {name: /save curation/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    expect(onCreateShare.mock.calls[0][1]).toBe('My picks');
    await waitFor(() => expect(storedDraft()).toBeNull());
  });

  it('keeps the projects a narrowed search left out of the saved curation in the draft', async () => {
    storeDraft(
      [
        makeRow({team_number: 'T01', project_title: 'Project 1', organization: 'Acme'}),
        makeRow({team_number: 'T02', project_title: 'Project 2', organization: 'Globex'}),
        makeRow({team_number: 'T03', project_title: 'Project 3', organization: 'Initech'}),
      ],
      {owner: 'member-1', name: 'Acme picks', note: 'For Acme'},
    );
    const onCreateShare = vi.fn().mockResolvedValue({id: 'share-acme'});
    const {unmount} = render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />,
    );

    const merged = within(getMergedSection() as HTMLElement);
    fireEvent.change(merged.getByRole('searchbox', {name: 'Search this list'}), {target: {value: 'Acme'}});
    expect(merged.getByText(/after saving, 2 other projects stay in this draft\./)).toBeInTheDocument();
    fireEvent.click(merged.getAllByRole('button', {name: /save curation/i})[0]);

    await waitFor(() => expect(onCreateShare).toHaveBeenCalledTimes(1));
    expect((onCreateShare.mock.calls[0][0] as ProjectGridRow[]).map((row) => row.project_title)).toEqual(['Project 1']);
    // The saved project and the name and note it took with it leave the draft; the hidden ones stay.
    await waitFor(() =>
      expect(storedDraft()).toEqual({
        owner: 'member-1',
        rows: [
          expect.objectContaining({project_title: 'Project 2'}),
          expect.objectContaining({project_title: 'Project 3'}),
        ],
        name: '',
        note: '',
      }),
    );

    // Coming back to the builder (the save opened the curation, unmounting it) offers the rest.
    unmount();
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
    const restored = within(getMergedSection() as HTMLElement);
    expect(restored.getAllByText('Project 2').length).toBeGreaterThan(0);
    expect(restored.getAllByText('Project 3').length).toBeGreaterThan(0);
    expect(restored.queryByText('Project 1')).toBeNull();
  });

  it('keeps the draft when saving the curation fails', async () => {
    // The whole point of persistence is to not lose the user's merged rows; a failed save
    // (network error, 4xx/5xx) must leave the draft intact so they can retry.
    const onCreateShare = vi.fn().mockRejectedValue(new Error('boom'));
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={onCreateShare} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
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
});
