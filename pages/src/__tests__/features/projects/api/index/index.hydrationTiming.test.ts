import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

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
  PROJECT_DETAIL_CONCURRENCY,
  hydrateProjectGridRowsSettled,
  type ProjectGridRow,
  type ProjectTableRow,
} from '@/features/projects/api';
const makeTableRow = (overrides: Partial<ProjectTableRow> = {}): ProjectTableRow => ({
  id: 'project-1',
  semester_label: '2025-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Team A',
  project_title: 'Project A',
  organization: 'Org A',
  industry: 'Energy',
  abstract: 'An abstract',
  student_names: 'Alex',
  track: null,
  presentation_order: null,
  ...overrides,
});

describe('hydrateProjectGridRowsSettled retries and partial results', () => {
  const compactRow = (id: string): ProjectGridRow => ({id, ...makeGridRowBase(), project_title: `Compact ${id}`});
  const detail = (id: string) => ({data: makeTableRow({id, project_title: `Fetched ${id}`})});
  const httpError = (status?: number) => Object.assign(new Error('request failed'), status ? {response: {status}} : {});

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reports progress over the rows that needed a request', async () => {
    apiMock.get.mockImplementation(async (url: string) => detail(url.split('/').at(-2) as string));
    const onProgress = vi.fn();
    const complete = {...compactRow('done'), abstract: 'Has details'};

    await hydrateProjectGridRowsSettled([compactRow('p-1'), complete, compactRow('p-2')], {onProgress});

    expect(onProgress.mock.calls).toEqual([
      [1, 2],
      [2, 2],
    ]);
  });

  it('stops requesting once nothing has been answered for a while, and reports the rest as failed', async () => {
    // The API is down: every request fails without a response.
    apiMock.get.mockRejectedValue(httpError());
    const rows = Array.from({length: 200}, (_, index) => compactRow(`p-${index}`));

    const pending = hydrateProjectGridRowsSettled(rows);
    await vi.runAllTimersAsync();
    const {failedIndexes} = await pending;

    expect(failedIndexes).toHaveLength(200);
    // Each row takes 1.2 s of retries, so 6 at a time get through about 150 rows before failures have gone on
    // for 30 s; the rest are never requested (every row tried 3 times would be 600 requests).
    expect(apiMock.get.mock.calls.length).toBeLessThan(500);
    expect(apiMock.get).not.toHaveBeenCalledWith('/projects/p-199/', expect.anything());
  });

  it('does not give up on the remaining rows after the page was suspended mid-save', async () => {
    // A laptop sleeps for a minute: the requests in flight hang, then fail on waking, before the network is back.
    const wakeAt = Date.now() + 60_000;
    apiMock.get.mockImplementation(async (url: string) => {
      if (Date.now() < wakeAt) {
        await new Promise((resolve) => setTimeout(resolve, wakeAt - Date.now()));
        throw httpError();
      }
      if (Date.now() < wakeAt + 2_000) throw httpError();
      return detail(url.split('/').at(-2) as string);
    });
    const rows = Array.from({length: 20}, (_, index) => compactRow(`p-${index}`));

    const pending = hydrateProjectGridRowsSettled(rows);
    await vi.runAllTimersAsync();
    const {failedIndexes} = await pending;

    // Only the rows in flight during the sleep failed; the others were requested once it was over, and loaded.
    expect(failedIndexes).toEqual(Array.from({length: PROJECT_DETAIL_CONCURRENCY}, (_, index) => index));
  });

  it('keeps going while other rows load, however long one broken project takes', async () => {
    apiMock.get.mockImplementation(async (url: string) => {
      await new Promise((resolve) => setTimeout(resolve, 2_000));
      if (url === '/projects/p-0/') throw httpError(500);
      return detail(url.split('/').at(-2) as string);
    });
    const rows = Array.from({length: 120}, (_, index) => compactRow(`p-${index}`));

    const pending = hydrateProjectGridRowsSettled(rows);
    await vi.runAllTimersAsync();
    const {rows: loaded, failedIndexes} = await pending;

    // 120 rows at 2 s each, 4 at a time, run past 30 s; answers keep coming, so nothing is given up.
    expect(failedIndexes).toEqual([0]);
    expect(loaded[119].project_title).toBe('Fetched p-119');
  });

  it('rejects when its signal aborts instead of reporting rows as failed', async () => {
    const controller = new AbortController();
    apiMock.get.mockRejectedValueOnce(httpError(503));

    const pending = hydrateProjectGridRowsSettled([compactRow('p-1')], {signal: controller.signal});
    const assertion = expect(pending).rejects.toBeDefined();
    await vi.advanceTimersByTimeAsync(100);
    controller.abort();
    await assertion;
  });
});

const makeGridRowBase = (): Omit<ProjectGridRow, 'id'> => ({
  semester_label: '2025 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Team A',
  project_title: 'Project A',
  organization: 'Org A',
  industry: 'Energy',
  abstract: '',
  student_names: '',
  is_presenting: '',
});
