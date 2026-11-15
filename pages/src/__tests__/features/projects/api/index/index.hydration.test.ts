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

  it('retries a transient failure before giving up on a row', async () => {
    apiMock.get.mockRejectedValueOnce(httpError()).mockRejectedValueOnce(httpError(503)).mockResolvedValueOnce(detail('p-1'));

    const pending = hydrateProjectGridRowsSettled([compactRow('p-1')]);
    await vi.runAllTimersAsync();
    const {rows, failedIndexes} = await pending;

    expect(apiMock.get).toHaveBeenCalledTimes(3);
    expect(failedIndexes).toEqual([]);
    expect(rows[0].project_title).toBe('Fetched p-1');
  });

  it('keeps every row that loaded and reports the ones that still failed', async () => {
    apiMock.get.mockImplementation(async (url: string) => {
      if (url.includes('p-2')) throw httpError(500);
      return detail(url.split('/').at(-2) as string);
    });

    const pending = hydrateProjectGridRowsSettled([compactRow('p-1'), compactRow('p-2'), compactRow('p-3')]);
    await vi.runAllTimersAsync();
    const {rows, failedIndexes} = await pending;

    expect(failedIndexes).toEqual([1]);
    // 1 try + 2 retries for the failing row, 1 each for the others.
    expect(apiMock.get).toHaveBeenCalledTimes(5);
    expect(rows[0].project_title).toBe('Fetched p-1');
    expect(rows[1].project_title).toBe('Compact p-2');
    expect(rows[2].project_title).toBe('Fetched p-3');
  });

  it('reports a missing project as unavailable without retrying it', async () => {
    apiMock.get.mockRejectedValue(httpError(404));

    const {failedIndexes, unavailableIndexes} = await hydrateProjectGridRowsSettled([compactRow('gone')]);

    expect(apiMock.get).toHaveBeenCalledTimes(1);
    expect(failedIndexes).toEqual([]);
    expect(unavailableIndexes).toEqual([0]);
  });

  it('gives each detail request a timeout, which is retried like a network failure', async () => {
    apiMock.get.mockRejectedValueOnce(Object.assign(new Error('timeout of 15000ms exceeded'), {code: 'ECONNABORTED'}));
    apiMock.get.mockResolvedValueOnce(detail('p-1'));

    const pending = hydrateProjectGridRowsSettled([compactRow('p-1')]);
    await vi.runAllTimersAsync();
    const {rows, failedIndexes} = await pending;

    expect(apiMock.get).toHaveBeenCalledWith('/projects/p-1/', expect.objectContaining({timeout: 15_000}));
    expect(failedIndexes).toEqual([]);
    expect(rows[0].project_title).toBe('Fetched p-1');
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
