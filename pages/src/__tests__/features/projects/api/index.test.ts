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
  hydrateProjectGridRows,
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

    const result = await hydrateProjectGridRows([
      {id: 'project-1', ...makeGridRowBase(), abstract: '', student_names: ''},
      alreadyHydrated,
      noId,
    ]);

    expect(apiMock.get).toHaveBeenCalledTimes(1);
    expect(apiMock.get).toHaveBeenCalledWith('/projects/project-1/', expect.objectContaining({}));
    expect(result).toHaveLength(3);
    expect(result[0].project_title).toBe('Fetched');
    expect(result[1]).toEqual(alreadyHydrated);
    expect(result[2]).toEqual(noId);
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
