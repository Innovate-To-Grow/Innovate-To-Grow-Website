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
  createPastProjectShare,
  deleteShare,
  fetchPastProjectShare,
  listMyShares,
  updatePastProjectShare,
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
