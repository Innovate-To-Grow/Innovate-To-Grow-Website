import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api: apiMock,
}));

import {fetchLatestNews, fetchNews, fetchNewsDetail} from '@/features/news/api';

describe('news API', () => {
  beforeEach(() => {
    apiMock.get.mockReset();
  });

  it('fetches paginated news with defaults and explicit pagination', async () => {
    apiMock.get.mockResolvedValue({data: {results: []}});

    await fetchNews();
    await fetchNews(3, 6);

    expect(apiMock.get).toHaveBeenNthCalledWith(1, '/news/?page=1&page_size=12');
    expect(apiMock.get).toHaveBeenNthCalledWith(2, '/news/?page=3&page_size=6');
  });

  it('returns the latest news article or null', async () => {
    apiMock.get.mockResolvedValueOnce({data: {results: [{id: 'news-1', title: 'Launch'}]}});

    await expect(fetchLatestNews()).resolves.toEqual({id: 'news-1', title: 'Launch'});

    apiMock.get.mockResolvedValueOnce({data: {results: []}});
    await expect(fetchLatestNews()).resolves.toBeNull();
  });

  it('fetches news detail by id', async () => {
    apiMock.get.mockResolvedValue({data: {id: 'news-1', title: 'Launch'}});

    await expect(fetchNewsDetail('news-1')).resolves.toEqual({id: 'news-1', title: 'Launch'});

    expect(apiMock.get).toHaveBeenCalledWith('/news/news-1/');
  });
});
