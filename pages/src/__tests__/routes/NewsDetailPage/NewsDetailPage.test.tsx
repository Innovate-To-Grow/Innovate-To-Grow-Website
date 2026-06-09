import {render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {NewsDetailPage} from '@/routes/NewsDetailPage/NewsDetailPage';
import type {NewsArticle} from '@/features/news';

const newsDetailMocks = vi.hoisted(() => ({
  fetchNewsDetail: vi.fn(),
}));

vi.mock('@/features/news', async () => {
  const actual = await vi.importActual<typeof import('@/features/news')>('@/features/news');
  return {
    ...actual,
    fetchNewsDetail: newsDetailMocks.fetchNewsDetail,
  };
});

const article = (overrides: Partial<NewsArticle> = {}): NewsArticle => ({
  id: '1',
  title: 'I2G News',
  source_url: 'javascript:alert(1)',
  summary: 'Summary content',
  image_url: '',
  author: 'News Author',
  published_at: '2026-05-01T12:00:00Z',
  content: '<p>Full <strong>story</strong></p>',
  hero_image_url: 'https://example.com/hero.jpg',
  hero_caption: 'Hero caption',
  ...overrides,
});

const renderDetail = (route = '/news/1') =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/news/:id" element={<NewsDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('NewsDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    newsDetailMocks.fetchNewsDetail.mockResolvedValue(article());
  });

  it('renders article detail content and sanitizes the source link', async () => {
    renderDetail();

    await waitFor(() => expect(newsDetailMocks.fetchNewsDetail).toHaveBeenCalledWith('1'));
    expect(await screen.findByRole('heading', {name: 'I2G News'})).toBeInTheDocument();
    expect(screen.getByText('Hero caption')).toBeInTheDocument();
    expect(screen.getByText('News Author')).toBeInTheDocument();
    expect(screen.getByText('Full')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'View original article'})).toHaveAttribute('href', '#');
  });

  it('falls back to summary content and shows failures', async () => {
    newsDetailMocks.fetchNewsDetail.mockResolvedValueOnce(article({content: '', hero_image_url: '', summary: 'Only summary'}));
    const summary = renderDetail();
    expect(await screen.findByText('Only summary')).toBeInTheDocument();
    summary.unmount();

    newsDetailMocks.fetchNewsDetail.mockRejectedValueOnce(new Error('offline'));
    renderDetail();
    expect(await screen.findByText('Unable to load this article.')).toBeInTheDocument();
  });
});
