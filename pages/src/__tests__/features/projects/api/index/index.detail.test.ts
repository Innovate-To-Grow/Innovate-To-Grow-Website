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
  PROJECT_DETAIL_CONCURRENCY,
  fetchProjectDetail,
  hydrateProjectGridRowsSettled,
  rememberProjectDetail,
  searchPastProjectsWithAI,
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

describe('project archive and detail fetch helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
      scope: 'past',
    });
  });

  it('searches past projects with AI with a custom limit', async () => {
    authApiMock.post.mockResolvedValue({data: {available: true, query: 'solar', results: []}});
    await searchPastProjectsWithAI('solar', 25);
    expect(authApiMock.post).toHaveBeenCalledWith('/projects/past-ai-search/', {
      query: 'solar',
      limit: 25,
      scope: 'past',
    });
  });

  it('fetches a single project detail with an optional abort signal', async () => {
    const signal = new AbortController().signal;
    apiMock.get.mockResolvedValue({data: {id: 'project-1'}});
    await expect(fetchProjectDetail('project-1', signal)).resolves.toEqual({id: 'project-1'});
    expect(apiMock.get).toHaveBeenCalledWith('/projects/project-1/', {signal});
  });

  it('requests a project id as one path segment, so a crafted link cannot reach another endpoint', async () => {
    apiMock.get.mockResolvedValue({data: {id: 'x'}});

    await fetchProjectDetail('../../event/projects');
    await fetchProjectDetail('abc?x=1', undefined, 5000);

    expect(apiMock.get).toHaveBeenNthCalledWith(1, '/projects/..%2F..%2Fevent%2Fprojects/', {signal: undefined});
    expect(apiMock.get).toHaveBeenNthCalledWith(2, '/projects/abc%3Fx%3D1/', {signal: undefined, timeout: 5000});
  });

  it('does not request again the details a row already loaded', async () => {
    rememberProjectDetail({...makeTableRow({id: 'cached-1', project_title: 'Cached'}), abstract: 'Cached abstract'});
    apiMock.get.mockResolvedValue({data: makeTableRow({id: 'fresh-1', project_title: 'Fresh'})});

    const {rows: result} = await hydrateProjectGridRowsSettled([
      {id: 'cached-1', ...makeGridRowBase(), abstract: '', student_names: ''},
      {id: 'fresh-1', ...makeGridRowBase(), abstract: '', student_names: ''},
    ]);

    expect(apiMock.get).toHaveBeenCalledTimes(1);
    expect(apiMock.get).toHaveBeenCalledWith('/projects/fresh-1/', expect.anything());
    expect(result.map((row) => [row.project_title, row.abstract])).toEqual([
      ['Cached', 'Cached abstract'],
      ['Fresh', 'An abstract'],
    ]);
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
    expect(peak).toBe(PROJECT_DETAIL_CONCURRENCY);
    expect(apiMock.get).toHaveBeenCalledTimes(20);
    expect(result).toHaveLength(20);
    expect(result[0].project_title).toBe('Fetched project-0');
    expect(result[19].project_title).toBe('Fetched project-19');
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
