import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {authenticatedAuth, getMergedSection, ROWS} from '@/__tests__/features/projects/components/builder/composition/fixtures/pastProjectsBuilderFixtures';

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

  describe('with the builder open in another tab too', () => {
    // The storage event fires only in the tabs that did not write, carrying the new value.
    const writeFromOtherTab = (value: unknown) =>
      act(() => {
        const newValue = value === null ? null : JSON.stringify(value);
        if (newValue === null) localStorage.removeItem(DRAFT_STORAGE_KEY);
        else localStorage.setItem(DRAFT_STORAGE_KEY, newValue);
        window.dispatchEvent(new StorageEvent('storage', {key: DRAFT_STORAGE_KEY, newValue, storageArea: localStorage}));
      });

    it("follows the other tab's changes, so its next save does not overwrite them", () => {
      storeDraft([ROWS[0]], {owner: 'member-1'});
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

      // The other tab adds Bravo and names the draft. This tab does not write it back (tabs answering each
      // other's writes would never stop).
      const fromTabB = {owner: 'member-1', rows: [ROWS[1], ROWS[0]], name: 'From tab B', note: ''};
      const setItem = vi.spyOn(Storage.prototype, 'setItem');
      writeFromOtherTab(fromTabB);
      expect(setItem).toHaveBeenCalledTimes(1);
      setItem.mockRestore();
      const merged = within(getMergedSection() as HTMLElement);
      expect(merged.getAllByText('Bravo Project').length).toBeGreaterThan(0);
      expect(screen.getByLabelText(/curation name/i)).toHaveValue('From tab B');
      expect(screen.getByText(/The curation draft was changed in another tab/)).toBeInTheDocument();

      // This tab then adds Charlie: the stored draft has all three.
      fireEvent.click(screen.getAllByLabelText('Select Charlie Project')[0]);
      fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
      expect(storedDraft()?.rows.map((row) => row.project_title)).toEqual([
        'Bravo Project',
        'Alpha Project',
        'Charlie Project',
      ]);
      expect(storedDraft()?.name).toBe('From tab B');
    });

    it("keeps this tab's checked rows checked, and empties when the other tab clears the draft", () => {
      storeDraft([ROWS[0], ROWS[1]], {owner: 'member-1'});
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      const merged = within(getMergedSection() as HTMLElement);
      fireEvent.click(merged.getAllByLabelText('Select Alpha Project')[0]);

      writeFromOtherTab({owner: 'member-1', rows: [ROWS[0], ROWS[1], ROWS[2]], name: '', note: ''});
      expect(merged.getAllByLabelText('Select Alpha Project')[0]).toBeChecked();

      writeFromOtherTab(null);
      expect(getMergedSection()).toBeNull();
      expect(storedDraft()).toBeNull();
    });

    it("ignores another member's draft and a value it cannot read", () => {
      storeDraft([ROWS[0]], {owner: 'member-1'});
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

      writeFromOtherTab({owner: 'member-2', rows: [ROWS[1]], name: 'Not yours', note: ''});
      act(() => {
        window.dispatchEvent(new StorageEvent('storage', {key: DRAFT_STORAGE_KEY, newValue: '{not json'}));
      });

      const merged = within(getMergedSection() as HTMLElement);
      expect(merged.getAllByText('Alpha Project').length).toBeGreaterThan(0);
      expect(merged.queryByText('Bravo Project')).toBeNull();
      expect(screen.getByLabelText(/curation name/i)).toHaveValue('');
    });
  });

  it('ignores a malformed kept draft', () => {
    localStorage.setItem(DRAFT_STORAGE_KEY, '{not valid json');

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(getMergedSection()).toBeNull();
  });
});
