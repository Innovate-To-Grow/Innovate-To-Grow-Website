import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({get: vi.fn()}));

vi.mock('@/lib/api', () => ({api: apiMock}));
// The shared test setup stubs the list searches; this file tests the real ones.
vi.unmock('@/features/projects/api/archive');

import {
  MAX_ARCHIVE_SEARCH_MATCHES,
  fetchAllProjectsCatalog,
  fetchCatalogPage,
  searchAllProjectIds,
} from '@/features/projects/api/archive';

const CURRENT_ID = '33333333-3333-4333-8333-333333333333';

const page = (count: number, results: Array<Record<string, unknown>>) => ({
  data: {count, next: null, previous: null, results},
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('fetchCatalogPage', () => {
  it('asks the list it names for one page, with the query, the signal and the request timeout', async () => {
    const signal = new AbortController().signal;
    apiMock.get.mockResolvedValue(page(0, []));

    await expect(fetchCatalogPage('/projects/all/', {page: 2, page_size: 50, search: 'solar'}, signal)).resolves.toEqual(
      page(0, []).data,
    );
    expect(apiMock.get).toHaveBeenCalledWith('/projects/all/', {
      params: {page: 2, page_size: 50, search: 'solar'},
      signal,
      timeout: 15_000,
    });
  });
});

describe('fetchAllProjectsCatalog', () => {
  it('loads every /projects/all/ page, the ones after the first together, in page order', async () => {
    const signal = new AbortController().signal;
    const pending = new Map<number, (results: Array<{id: string}>) => void>();
    apiMock.get.mockImplementation((_url: string, {params}: {params: {page: number}}) =>
      params.page === 1
        ? Promise.resolve(page(250, [{id: 'p1'}]))
        : new Promise((resolve) => {
            pending.set(params.page, (results) => resolve(page(250, results)));
          }),
    );

    const loaded = fetchAllProjectsCatalog({season: 2}, signal);
    await vi.waitFor(() => expect(pending.size).toBe(2));
    expect(apiMock.get.mock.calls.map(([url, config]) => [url, config.params, config.signal === signal])).toEqual([
      ['/projects/all/', {season: 2, page: 1, page_size: 100}, true],
      ['/projects/all/', {season: 2, page: 2, page_size: 100}, true],
      ['/projects/all/', {season: 2, page: 3, page_size: 100}, true],
    ]);

    pending.get(3)?.([{id: 'p3'}]);
    pending.get(2)?.([{id: 'p2'}]);
    await expect(loaded).resolves.toEqual([{id: 'p1'}, {id: 'p2'}, {id: 'p3'}]);
  });

  it('keeps one copy of a row that two pages both hold, since the list can shift between their requests', async () => {
    apiMock.get.mockImplementation((_url: string, {params}: {params: {page: number}}) =>
      Promise.resolve(
        page(
          200,
          params.page === 1
            ? [{id: 'a', project_title: 'First copy'}, {id: 'b'}]
            : [{id: 'b'}, {id: 'a', project_title: 'Second copy'}, {id: 'c'}],
        ),
      ),
    );

    const rows = await fetchAllProjectsCatalog();

    expect(rows.map((row) => row.id)).toEqual(['a', 'b', 'c']);
    expect(rows[0].project_title).toBe('First copy');
  });

  it('drops a current project that an archive row on another page now stands in for', async () => {
    // The team's semester was imported between the two requests: page 1 still listed it as a current project, and
    // page 2 lists its archive row, which names it in current_project_id.
    const standIn = {id: 'archived', catalog: 'archive', current_project_id: CURRENT_ID};
    apiMock.get.mockImplementation((_url: string, {params}: {params: {page: number}}) =>
      Promise.resolve(
        page(200, params.page === 1 ? [{id: CURRENT_ID, catalog: 'current'}, {id: 'other'}] : [standIn]),
      ),
    );

    await expect(fetchAllProjectsCatalog()).resolves.toEqual([{id: 'other'}, standIn]);
  });
});

describe('searchAllProjectIds', () => {
  it("asks /projects/all/ for a search's matches on every page and returns their ids", async () => {
    const signal = new AbortController().signal;
    apiMock.get.mockImplementation((_url: string, {params}: {params: {page: number}}) =>
      Promise.resolve(page(150, [{id: `match-${params.page}`, catalog: params.page === 1 ? 'current' : 'archive'}])),
    );

    await expect(searchAllProjectIds('Abstract-101', signal)).resolves.toEqual(new Set(['match-1', 'match-2']));
    expect(apiMock.get.mock.calls.map(([url, config]) => [url, config.params, config.signal === signal])).toEqual([
      ['/projects/all/', {search: 'Abstract-101', page: 1, page_size: 100}, true],
      ['/projects/all/', {search: 'Abstract-101', page: 2, page_size: 100}, true],
    ]);
  });

  it('finds a current project by the archive row that stands in for it, for a list loaded before the import', async () => {
    apiMock.get.mockResolvedValue(page(1, [{id: 'archived', catalog: 'archive', current_project_id: CURRENT_ID}]));

    await expect(searchAllProjectIds('irrigation')).resolves.toEqual(new Set(['archived', CURRENT_ID]));
  });

  it('declines, after one page, a search that matches more projects than a list fetches', async () => {
    apiMock.get.mockResolvedValue(page(MAX_ARCHIVE_SEARCH_MATCHES + 1, [{id: 'match-1'}]));

    await expect(searchAllProjectIds('the')).resolves.toBeNull();
    expect(apiMock.get).toHaveBeenCalledTimes(1);
  });
});
