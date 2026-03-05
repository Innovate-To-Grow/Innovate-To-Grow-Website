import api from './client';

export interface NewsArticle {
  id: string;
  title: string;
  source_url: string;
  summary: string;
  image_url: string;
  published_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const fetchNews = async (page = 1, pageSize = 12): Promise<PaginatedResponse<NewsArticle>> => {
  const response = await api.get<PaginatedResponse<NewsArticle>>(
    `/news/?page=${page}&page_size=${pageSize}`
  );
  return response.data;
};

export const fetchLatestNews = async (): Promise<NewsArticle | null> => {
  const response = await fetchNews(1, 1);
  return response.results[0] ?? null;
};
