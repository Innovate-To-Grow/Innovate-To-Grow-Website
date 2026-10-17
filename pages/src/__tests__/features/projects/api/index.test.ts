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
vi.mock('@/features/auth', () => ({
  authApi: authApiMock,
  getAccessToken: mockGetAccessToken,
  isDefinitiveAuthFailure: mockIsDefinitiveAuthFailure,
}));

import {
  compactProjectToGridRow,
  createPastProjectShare,
  deleteShare,
  fetchCurrentProjects,
  fetchCurrentProjectsFull,
  fetchPastProjectArchive,
  fetchPastProjects,
  fetchPastProjectShare,
  fetchProjectDetail,
  hydrateProjectGridRowsSettled,
  listMyShares,
  scheduleProjectToGridRow,
  searchPastProjectsWithAI,
  toProjectGridRow,
  updatePastProjectShare,
  type ProjectGridRow,
  type ProjectTableRow,
} from '@/features/projects/api';

const rows = [
  {
    semester_label: 'Spring 2026',
    class_code: 'ENGR 190',
    team_number: '1',
    team_name: 'Growers',
    project_title: 'Irrigation Monitor',
    organization: 'UC Merced',
    industry: 'Agriculture',
    abstract: 'A project abstract',
    student_names: 'Student One',
    is_presenting: 'Yes',
  },
];

describe('past project share API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetAccessToken.mockReturnValue('access-token');
  });

  it('uses the public client directly for anonymous share reads', async () => {
    mockGetAccessToken.mockReturnValue(null);
    apiMock.get.mockResolvedValue({data: {id: 'share-1', can_edit: false}});

    await expect(fetchPastProjectShare('share-1')).resolves.toEqual({
      id: 'share-1',
      can_edit: false,
    });
    expect(apiMock.get).toHaveBeenCalledWith('/projects/past-shares/share-1/');
    expect(authApiMock.get).not.toHaveBeenCalled();
  });

  it('uses the auth client for signed-in share reads', async () => {
    authApiMock.get.mockResolvedValue({data: {id: 'share-1', can_edit: true}});

    await expect(fetchPastProjectShare('share-1')).resolves.toEqual({
      id: 'share-1',
      can_edit: true,
    });
    expect(authApiMock.get).toHaveBeenCalledWith(
      '/projects/past-shares/share-1/',
      {requireFreshIdentity: true},
    );
    expect(apiMock.get).not.toHaveBeenCalled();
  });

  it('retries anonymously after a definitive refresh rejection', async () => {
    authApiMock.get.mockRejectedValue({
      response: {status: 401},
      definitive: true,
    });
    apiMock.get.mockResolvedValue({data: {id: 'share-1'}});

    await expect(fetchPastProjectShare('share-1')).resolves.toEqual({
      id: 'share-1',
    });
    expect(apiMock.get).toHaveBeenCalledWith('/projects/past-shares/share-1/');
  });

  it.each([
    [{response: {status: 401}}, 'transient refresh failure'],
    [{response: {status: 403}, definitive: true}, 'non-401 failure'],
  ])('does not fall back publicly after a %s', async (...[error]) => {
    authApiMock.get.mockRejectedValue(error);

    await expect(fetchPastProjectShare('share-1')).rejects.toBe(error);
    expect(apiMock.get).not.toHaveBeenCalled();
  });

  it('creates a share with the snake_case snapshot contract', async () => {
    const data = {id: 'share-1', rows, version: 1, share_url: '/share-1'};
    authApiMock.post.mockResolvedValue({data});

    await expect(
      createPastProjectShare(rows, 'Faculty picks', 'Review these projects'),
    ).resolves.toBe(data);
    expect(authApiMock.post).toHaveBeenCalledWith('/projects/past-shares/', {
      rows,
      name: 'Faculty picks',
      note: 'Review these projects',
    });
  });

  it('updates a share with its optimistic-lock version', async () => {
    const payload = {name: 'Updated picks', rows, note: 'Updated', version: 4};
    const data = {id: 'share-1', ...payload, version: 5};
    authApiMock.patch.mockResolvedValue({data});

    await expect(updatePastProjectShare('share-1', payload)).resolves.toBe(data);
    expect(authApiMock.patch).toHaveBeenCalledWith(
      '/projects/past-shares/share-1/',
      payload,
    );
  });

  it('lists the signed-in member shares with snake_case summaries', async () => {
    const data = [
      {
        id: 'share-1',
        name: 'Faculty picks',
        note: '',
        version: 3,
        share_url: '/share-1',
        row_count: 1,
        created_at: '2026-08-12T00:00:00Z',
      },
    ];
    authApiMock.get.mockResolvedValue({data});

    await expect(listMyShares()).resolves.toBe(data);
    expect(authApiMock.get).toHaveBeenCalledWith(
      '/projects/past-shares/mine/',
    );
  });

  it('deletes a share through the authenticated endpoint', async () => {
    authApiMock.delete.mockResolvedValue({status: 204});

    await expect(deleteShare('share-1')).resolves.toBeUndefined();
    expect(authApiMock.delete).toHaveBeenCalledWith(
      '/projects/past-shares/share-1/',
    );
  });
});

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

describe('project grid row mappers', () => {
  it('maps a table row to a grid row and formats the semester label', () => {
    expect(toProjectGridRow(makeTableRow({is_presenting: undefined}))).toMatchObject({
      id: 'project-1',
      semester_label: '2025 Spring',
      is_presenting: '',
    });
    expect(toProjectGridRow(makeTableRow({is_presenting: true})).is_presenting).toBe('Yes');
    expect(toProjectGridRow(makeTableRow({is_presenting: false})).is_presenting).toBe('No');
  });

  it('maps a schedule row without an id and normalizes is_presenting', () => {
    const scheduleRow = {
      id: 'schedule-1',
      track: 1,
      order: 2,
      year_semester: '2025-1 Spring',
      class_code: 'CAP',
      team_number: '101',
      team_name: 'Team A',
      project_title: 'Project A',
      organization: 'Org A',
      industry: 'Energy',
      abstract: 'An abstract',
      student_names: 'Alex',
      is_presenting: true,
      tooltip: '',
    };
    expect(scheduleProjectToGridRow(scheduleRow)).toMatchObject({
      semester_label: '2025 Spring',
      is_presenting: 'Yes',
    });
    expect(scheduleProjectToGridRow(scheduleRow)).not.toHaveProperty('id');
    expect(scheduleProjectToGridRow({...scheduleRow, is_presenting: false}).is_presenting).toBe('No');
  });

  it('maps a compact archive row with empty detail fields', () => {
    expect(
      compactProjectToGridRow({
        id: 'project-1',
        semester_label: '2025-1 Spring',
        class_code: 'CAP',
        team_number: '101',
        team_name: 'Team A',
        project_title: 'Project A',
        organization: 'Org A',
        industry: 'Energy',
        track: null,
        presentation_order: null,
      }),
    ).toEqual({
      id: 'project-1',
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
  });
});

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
    });
  });

  it('uses empty defaults for the archive query', async () => {
    apiMock.get.mockResolvedValue({data: {results: []}});
    await fetchPastProjectArchive();
    expect(apiMock.get).toHaveBeenCalledWith('/projects/archive/', {
      params: {},
      signal: undefined,
    });
  });

  it('fetches the legacy past projects endpoint with page query params', async () => {
    apiMock.get.mockResolvedValue({data: {results: []}});
    await expect(fetchPastProjects(3, 25)).resolves.toEqual({results: []});
    expect(apiMock.get).toHaveBeenCalledWith('/projects/past/?page=3&page_size=25');
  });

  it('searches past projects with AI via the auth client and default limit', async () => {
    authApiMock.post.mockResolvedValue({data: {available: true, query: 'solar', results: []}});
    await expect(searchPastProjectsWithAI('solar')).resolves.toEqual({
      available: true,
      query: 'solar',
      results: [],
    });
    expect(authApiMock.post).toHaveBeenCalledWith('/projects/past-ai-search/', {
      query: 'solar',
      limit: 10,
    });
  });

  it('searches past projects with AI with a custom limit', async () => {
    authApiMock.post.mockResolvedValue({data: {available: true, query: 'solar', results: []}});
    await searchPastProjectsWithAI('solar', 25);
    expect(authApiMock.post).toHaveBeenCalledWith('/projects/past-ai-search/', {
      query: 'solar',
      limit: 25,
    });
  });

  it('fetches a single project detail with an optional abort signal', async () => {
    const signal = new AbortController().signal;
    apiMock.get.mockResolvedValue({data: {id: 'project-1'}});
    await expect(fetchProjectDetail('project-1', signal)).resolves.toEqual({id: 'project-1'});
    expect(apiMock.get).toHaveBeenCalledWith('/projects/project-1/', {signal});
  });

  it('hydrates only the rows that need it and leaves the rest untouched', async () => {
    const alreadyHydrated: ProjectGridRow = {
      id: 'project-2',
      semester_label: '2025 Spring',
      class_code: 'CAP',
      team_number: '102',
      team_name: 'Team B',
      project_title: 'Project B',
      organization: 'Org B',
      industry: 'Water',
      abstract: 'Already present',
      student_names: 'Sam',
      is_presenting: '',
    };
    const noId: ProjectGridRow = {...alreadyHydrated, id: undefined, abstract: '', student_names: ''};
    apiMock.get.mockResolvedValue({data: makeTableRow({id: 'project-1', project_title: 'Fetched'})});

    const {rows: result, failedIndexes} = await hydrateProjectGridRowsSettled([
      {id: 'project-1', ...makeGridRowBase(), abstract: '', student_names: ''},
      alreadyHydrated,
      noId,
    ]);

    expect(failedIndexes).toEqual([]);
    expect(apiMock.get).toHaveBeenCalledTimes(1);
    expect(apiMock.get).toHaveBeenCalledWith('/projects/project-1/', expect.objectContaining({}));
    expect(result).toHaveLength(3);
    expect(result[0].project_title).toBe('Fetched');
    expect(result[1]).toEqual(alreadyHydrated);
    expect(result[2]).toEqual(noId);
  });

  it('bounds the detail requests it opens at once and preserves row order', async () => {
    let open = 0;
    let peak = 0;
    apiMock.get.mockImplementation(async (url: string) => {
      open += 1;
      peak = Math.max(peak, open);
      // Yield so every worker that is allowed to run gets a chance to start.
      await Promise.resolve();
      await Promise.resolve();
      open -= 1;
      const id = url.split('/').at(-2) as string;
      return {data: makeTableRow({id, project_title: `Fetched ${id}`})};
    });

    const rows: ProjectGridRow[] = Array.from({length: 20}, (_, index) => ({
      id: `project-${index}`,
      ...makeGridRowBase(),
      abstract: '',
      student_names: '',
    }));

    const {rows: result} = await hydrateProjectGridRowsSettled(rows);

    // Selecting a large page of archive rows must not open one request per row at once.
    expect(peak).toBeLessThanOrEqual(4);
    expect(apiMock.get).toHaveBeenCalledTimes(20);
    expect(result).toHaveLength(20);
    expect(result[0].project_title).toBe('Fetched project-0');
    expect(result[19].project_title).toBe('Fetched project-19');
  });
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
    // Each row takes 1.2 s of retries, so 4 at a time get through about 100 rows before 30 s pass without an
    // answer; the rest are never requested (every row tried 3 times would be 600 requests).
    expect(apiMock.get.mock.calls.length).toBeLessThan(400);
    expect(apiMock.get).not.toHaveBeenCalledWith('/projects/p-199/', expect.anything());
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
