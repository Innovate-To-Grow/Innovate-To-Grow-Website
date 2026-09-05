import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {get: mocks.get},
}));

import {fetchLatestNews, fetchNews, fetchNewsDetail} from '@/features/news/api';

describe('news api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('fetchNews', () => {
    it('fetches with default pagination', async () => {
      mocks.get.mockResolvedValue({data: {results: [], count: 0}});

      await fetchNews();

      expect(mocks.get).toHaveBeenCalledWith('/news/?page=1&page_size=12');
    });

    it('passes custom pagination', async () => {
      mocks.get.mockResolvedValue({data: {results: [], count: 0}});

      await fetchNews(3, 20);

      expect(mocks.get).toHaveBeenCalledWith('/news/?page=3&page_size=20');
    });

    it('returns the response data', async () => {
      const data = {results: [{id: '1'}], count: 1};
      mocks.get.mockResolvedValue({data});

      await expect(fetchNews()).resolves.toBe(data);
    });
  });

  describe('fetchLatestNews', () => {
    it('returns the first result', async () => {
      const article = {id: '1', title: 'Latest'};
      mocks.get.mockResolvedValue({data: {results: [article], count: 1}});

      await expect(fetchLatestNews()).resolves.toEqual(article);
    });

    it('returns null when there are no results', async () => {
      mocks.get.mockResolvedValue({data: {results: [], count: 0}});

      await expect(fetchLatestNews()).resolves.toBeNull();
    });
  });

  describe('fetchNewsDetail', () => {
    it('fetches by id without a signal', async () => {
      mocks.get.mockResolvedValue({data: {id: '1'}});

      await fetchNewsDetail('1');

      expect(mocks.get).toHaveBeenCalledWith('/news/1/', {signal: undefined});
    });

    it('forwards an AbortSignal', async () => {
      const signal = new AbortController().signal;
      mocks.get.mockResolvedValue({data: {id: '1'}});

      await fetchNewsDetail('1', signal);

      expect(mocks.get).toHaveBeenCalledWith('/news/1/', {signal});
    });
  });
});
