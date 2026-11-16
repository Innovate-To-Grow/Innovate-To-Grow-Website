import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
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
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
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

  it('takes only the member id from the auth context into the kept draft', () => {
    // The auth context also carries the member's contact details and the password-flow actions; none of
    // that may end up in localStorage with the draft.
    mockUseAuth.mockReturnValue({
      ...authenticatedAuth,
      user: {
        member_uuid: 'member-1',
        email: 'draft-owner@example.com',
        phone: '+12025550199',
        first_name: 'Draftfirst',
        last_name: 'Draftlast',
      },
      requestPasswordReset: vi.fn(),
      confirmPasswordReset: vi.fn(),
      confirmPasswordChange: vi.fn(),
    });
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    fireEvent.change(screen.getByLabelText(/curation name/i), {target: {value: 'My picks'}});

    const raw = localStorage.getItem(DRAFT_STORAGE_KEY) as string;
    expect(Object.keys(JSON.parse(raw)).sort()).toEqual(['name', 'note', 'owner', 'rows']);
    expect(storedDraft()?.owner).toBe('member-1');
    for (const detail of ['draft-owner@example.com', '+12025550199', 'Draftfirst', 'Draftlast']) {
      expect(raw).not.toContain(detail);
    }
  });

  it('rewrites a kept draft without anything an earlier version stored beside it', () => {
    localStorage.setItem(
      DRAFT_STORAGE_KEY,
      JSON.stringify({
        owner: 'member-1',
        rows: [makeRow({team_number: 'T09', project_title: 'Persisted Project'})],
        name: 'Water picks',
        note: '',
        password: 'not-a-real-password',
        access: 'not-a-real-access-token',
        user: {email: 'draft-owner@example.com'},
      }),
    );

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(within(getMergedSection() as HTMLElement).getAllByText('Persisted Project').length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/curation name/i)).toHaveValue('Water picks');
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY) as string;
    expect(Object.keys(JSON.parse(raw)).sort()).toEqual(['name', 'note', 'owner', 'rows']);
    for (const leftover of ['not-a-real-password', 'not-a-real-access-token', 'draft-owner@example.com']) {
      expect(raw).not.toContain(leftover);
    }
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
});
