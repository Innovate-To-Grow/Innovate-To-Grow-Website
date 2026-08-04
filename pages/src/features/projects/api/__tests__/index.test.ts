import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
}));
const authApiMock = vi.hoisted(() => ({
  get: vi.fn(),
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

vi.mock('@/lib/api-client', () => ({api: apiMock}));
vi.mock('@/features/auth', () => ({
  authApi: authApiMock,
  getAccessToken: mockGetAccessToken,
  isDefinitiveAuthFailure: mockIsDefinitiveAuthFailure,
}));

import {fetchPastProjectShare} from '../index';

describe('fetchPastProjectShare auth fallback', () => {
  beforeEach(() => {
    apiMock.get.mockReset();
    authApiMock.get.mockReset();
    mockGetAccessToken.mockReset();
    mockGetAccessToken.mockReturnValue('access-token');
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
    expect(apiMock.get).toHaveBeenCalledWith(
      '/projects/past-shares/share-1/',
    );
  });

  it('does not replace authenticated data after a transient refresh failure', async () => {
    const error = {response: {status: 401}};
    authApiMock.get.mockRejectedValue(error);

    await expect(fetchPastProjectShare('share-1')).rejects.toBe(error);
    expect(apiMock.get).not.toHaveBeenCalled();
  });
});
