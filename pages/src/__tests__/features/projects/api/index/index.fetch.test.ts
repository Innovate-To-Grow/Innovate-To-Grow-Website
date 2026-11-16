import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
}));
const authApiMock = vi.hoisted(() => ({
  delete: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
}));
const mockGetAccessToken = vi.hoisted(() => vi.fn());
const mockIsDefinitiveAuthFailure = vi.hoisted(() =>
  vi.fn((error: unknown) =>
    Boolean(
      error &&
        typeof error === 'object' &&
        (error as {definitive?: boolean}).definitive,
    ),
  ),
);

vi.mock('@/lib/api', () => ({api: apiMock}));
// The shared test setup stubs the archive search; this file tests the real one.
vi.unmock('@/features/projects/api/archive');
vi.mock('@/features/auth', () => ({
  authApi: authApiMock,
  getAccessToken: mockGetAccessToken,
  isDefinitiveAuthFailure: mockIsDefinitiveAuthFailure,
}));

import {
  fetchAllPastProjectArchive,
  fetchCurrentProjects,
  fetchCurrentProjectsFull,
  fetchPastProjectArchive,
  fetchPastProjects,
  searchPastProjectArchiveIds,
} from '@/features/projects/api';
import {MAX_ARCHIVE_SEARCH_MATCHES} from '@/features/projects/api/archive';

describe('project archive and detail fetch helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches current projects through the public endpoint', async () => {
    apiMock.get.mockResolvedValue({data: {id: 'sem-1', projects: []}});
    await expect(fetchCurrentProjects()).resolves.toEqual({id: 'sem-1', projects: []});
    expect(apiMock.get).toHaveBeenCalledWith('/event/projects/');
  });

  it('fetches full current projects through the public endpoint', async () => {
    apiMock.get.mockResolvedValue({data: {id: 'sem-1', projects: []}});
    await expect(fetchCurrentProjectsFull()).resolves.toEqual({id: 'sem-1', projects: []});
    expect(apiMock.get).toHaveBeenCalledWith('/event/projects/');
  });

  it('passes archive query params and the abort signal through', async () => {
    const signal = new AbortController().signal;
    apiMock.get.mockResolvedValue({data: {results: []}});

    await expect(
      fetchPastProjectArchive({page: 2, page_size: 50, year: 2025, season: 1}, signal),
    ).resolves.toEqual({results: []});
    expect(apiMock.get).toHaveBeenCalledWith('/projects/archive/', {
      params: {page: 2, page_size: 50, year: 2025, season: 1},
      signal,
      timeout: 15_000,
    });
  });

  it('uses empty defaults for the archive query', async () => {
    apiMock.get.mockResolvedValue({data: {results: []}});
    await fetchPastProjectArchive();
    expect(apiMock.get).toHaveBeenCalledWith('/projects/archive/', {
      params: {},
      signal: undefined,
      timeout: 15_000,
    });
  });

  it('requests every archive page after the first at once, not one after another', async () => {
    const signal = new AbortController().signal;
    const pending = new Map<number, (results: {id: string}[]) => void>();
    apiMock.get.mockImplementation((_url: string, {params}: {params: {page: number}}) =>
      params.page === 1
        ? Promise.resolve({data: {count: 250, next: null, previous: null, results: [{id: 'p1'}]}})
        : new Promise((resolve) => {
            pending.set(params.page, (results) => resolve({data: {count: 250, next: null, previous: null, results}}));
          }),
    );

    const loaded = fetchAllPastProjectArchive({year: 2025}, signal);
    // Pages 2 and 3 are both requested before either answers.
    await vi.waitFor(() => expect(pending.size).toBe(2));
    expect(apiMock.get.mock.calls.map(([, config]) => config.params)).toEqual([
      {year: 2025, page: 1, page_size: 100},
      {year: 2025, page: 2, page_size: 100},
      {year: 2025, page: 3, page_size: 100},
    ]);
    expect(apiMock.get.mock.calls.every(([, config]) => config.signal === signal)).toBe(true);

    // The rows keep page order whichever page answers first.
    pending.get(3)?.([{id: 'p3'}]);
    pending.get(2)?.([{id: 'p2'}]);
    await expect(loaded).resolves.toEqual([{id: 'p1'}, {id: 'p2'}, {id: 'p3'}]);
  });

  it('makes a single request for an archive that fits on one page', async () => {
    apiMock.get.mockResolvedValue({data: {count: 2, next: null, previous: null, results: [{id: 'a'}, {id: 'b'}]}});

    await expect(fetchAllPastProjectArchive()).resolves.toEqual([{id: 'a'}, {id: 'b'}]);
    expect(apiMock.get).toHaveBeenCalledTimes(1);
  });

  it("asks the archive for a search's matches on every page and returns their ids", async () => {
    const signal = new AbortController().signal;
    apiMock.get.mockImplementation((_url: string, {params}: {params: {page: number}}) =>
      Promise.resolve({data: {count: 150, next: null, previous: null, results: [{id: `match-${params.page}`}]}}),
    );

    const ids = await searchPastProjectArchiveIds('EnergyPro', signal);

    expect(ids).toEqual(new Set(['match-1', 'match-2']));
    expect(apiMock.get.mock.calls.map(([url, config]) => [url, config.params, config.signal === signal])).toEqual([
      ['/projects/archive/', {search: 'EnergyPro', page: 1, page_size: 100}, true],
      ['/projects/archive/', {search: 'EnergyPro', page: 2, page_size: 100}, true],
    ]);
  });

  it('declines, after one page, a search the archive matches in more projects than a list fetches', async () => {
    // "the" is in 900 of 920 abstracts: its matches would be the whole archive again, and say nothing about it.
    apiMock.get.mockResolvedValue({
      data: {count: MAX_ARCHIVE_SEARCH_MATCHES + 1, next: null, previous: null, results: [{id: 'match-1'}]},
    });

    await expect(searchPastProjectArchiveIds('the')).resolves.toBeNull();
    expect(apiMock.get).toHaveBeenCalledTimes(1);

    apiMock.get.mockResolvedValue({data: {count: MAX_ARCHIVE_SEARCH_MATCHES, next: null, previous: null, results: []}});
    await expect(searchPastProjectArchiveIds('system')).resolves.toEqual(new Set());
    expect(apiMock.get).toHaveBeenCalledTimes(1 + MAX_ARCHIVE_SEARCH_MATCHES / 100);
  });

  it('fetches the legacy past projects endpoint with page query params', async () => {
    apiMock.get.mockResolvedValue({data: {results: []}});
    await expect(fetchPastProjects(3, 25)).resolves.toEqual({results: []});
    expect(apiMock.get).toHaveBeenCalledWith('/projects/past/?page=3&page_size=25');
  });
});
