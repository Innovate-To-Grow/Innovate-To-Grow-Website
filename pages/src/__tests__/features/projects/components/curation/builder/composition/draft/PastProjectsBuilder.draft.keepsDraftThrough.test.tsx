import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/curation/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {authenticatedAuth, getMergedSection, makeRow, ROWS} from '@/__tests__/features/projects/components/curation/builder/composition/fixtures/pastProjectsBuilderFixtures';

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
  const storeDraft = (rows: ProjectGridRow[], extra: {owner?: string | null; name?: string; note?: string} = {}) =>
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({owner: null, rows, name: '', note: '', ...extra}));
  const storedDraft = () => {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as {owner: string | null; rows: ProjectGridRow[]; name: string; note: string}) : null;
  };

  it('keeps the draft through revalidation and a temporary verification failure', () => {
    const builder = <PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />;
    const {rerender} = render(builder);
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
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
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
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
});
