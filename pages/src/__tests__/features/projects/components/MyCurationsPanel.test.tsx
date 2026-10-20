import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MyCurationsPanel} from '@/features/projects/components/MyCurationsPanel';
import type {PastProjectShareSummary} from '@/features/projects/api';

const mockUseAuth = vi.fn();
const mockListMyShares = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    listMyShares: () => mockListMyShares(),
  };
});

const member = (memberUuid: string) => ({
  isAuthenticated: true,
  isInitializing: false,
  user: {member_uuid: memberUuid, email: `${memberUuid}@example.com`},
});

const share = (overrides: Partial<PastProjectShareSummary>): PastProjectShareSummary => ({
  id: 'share-1',
  name: 'Water projects',
  note: '',
  version: 1,
  share_url: 'https://i2g.example/past-projects/share-1',
  row_count: 3,
  created_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-01T10:00:00Z',
  ...overrides,
});

const renderPanel = async () => {
  const view = render(
    <MemoryRouter>
      <MyCurationsPanel />
    </MemoryRouter>,
  );
  await act(async () => {});
  return view;
};

describe('MyCurationsPanel', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue(member('member-1'));
    mockListMyShares.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('lists saved curations, the most recently changed first, each opening its page', async () => {
    mockListMyShares.mockResolvedValue([
      share({id: 'old', name: 'Older list', updated_at: '2026-09-02T10:00:00Z'}),
      share({id: 'new', name: '', row_count: 1, updated_at: '2026-10-18T10:00:00-07:00'}),
      share({id: 'legacy', name: 'Legacy list', updated_at: undefined, created_at: '2026-09-10T10:00:00Z'}),
    ]);

    await renderPanel();

    const panel = screen.getByRole('region', {name: 'My Curations'});
    const links = within(panel).getAllByRole('link').filter((link) => link.getAttribute('href')?.startsWith('/past-projects/'));
    // An unnamed curation reads as the default title, as on its page.
    expect(links.map((link) => link.textContent)).toEqual(['Past Project Curation', 'Legacy list', 'Older list']);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/past-projects/new',
      '/past-projects/legacy',
      '/past-projects/old',
    ]);
    expect(within(panel).getByText('1 project · updated Oct 18, 2026')).toBeInTheDocument();
    expect(within(panel).getByText('3 projects · saved Sep 10, 2026')).toBeInTheDocument();
    expect(within(panel).getByRole('link', {name: 'Manage curations'})).toHaveAttribute(
      'href',
      '/account/past-project-curation-shared-links',
    );
  });

  it('shows the five most recent and links to the rest', async () => {
    mockListMyShares.mockResolvedValue(
      Array.from({length: 7}, (_, index) =>
        share({id: `s${index}`, name: `List ${index}`, updated_at: `2026-10-0${index + 1}T10:00:00Z`}),
      ),
    );

    await renderPanel();

    const panel = screen.getByRole('region', {name: 'My Curations'});
    expect(within(panel).getAllByRole('listitem')).toHaveLength(5);
    expect(within(panel).getByText('List 6')).toBeInTheDocument();
    expect(within(panel).queryByText('List 1')).toBeNull();
    expect(within(panel).getByRole('link', {name: 'See all 7'})).toHaveAttribute(
      'href',
      '/account/past-project-curation-shared-links',
    );
  });

  it('copies a curation link', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    mockListMyShares.mockResolvedValue([share({})]);

    await renderPanel();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Copy the link to Water projects'}));
    });

    expect(writeText).toHaveBeenCalledWith('https://i2g.example/past-projects/share-1');
    expect(screen.getByRole('status')).toHaveTextContent('Link copied.');
  });

  it('stays out of the way with no curations, a failed load, or no sign-in', async () => {
    mockListMyShares.mockResolvedValue([]);
    const empty = await renderPanel();
    expect(screen.queryByRole('region', {name: 'My Curations'})).toBeNull();
    empty.unmount();

    mockListMyShares.mockRejectedValue(new Error('offline'));
    const failed = await renderPanel();
    expect(screen.queryByRole('region', {name: 'My Curations'})).toBeNull();
    failed.unmount();

    mockListMyShares.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: false, isInitializing: false, user: null});
    await renderPanel();
    expect(mockListMyShares).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', {name: 'My Curations'})).toBeNull();
  });

  it("never shows one member's curations to the next account while its list loads", async () => {
    mockListMyShares.mockResolvedValueOnce([share({name: 'First member list'})]);
    const {rerender} = await renderPanel();
    expect(screen.getByText('First member list')).toBeInTheDocument();

    let finish!: (shares: PastProjectShareSummary[]) => void;
    mockListMyShares.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    mockUseAuth.mockReturnValue(member('member-2'));
    rerender(
      <MemoryRouter>
        <MyCurationsPanel />
      </MemoryRouter>,
    );
    expect(screen.queryByText('First member list')).toBeNull();

    await act(async () => finish([share({name: 'Second member list'})]));
    expect(screen.getByText('Second member list')).toBeInTheDocument();
  });
});
