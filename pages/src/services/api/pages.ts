import api from './client';

// ======================== Page Types ========================

export interface PageContent {
  id: number;
  title: string;
  slug: string;
  html: string;
  css: string;
  dynamic_config: Record<string, unknown>;
  meta_title: string;
  meta_description: string;
  meta_keywords: string;
  og_image: string | null;
  canonical_url: string | null;
  meta_robots: string;
  template_name: string;
  status?: 'draft' | 'review' | 'published';
  published: boolean;
  created_at: string;
  updated_at: string;
}

export const fetchPageContent = async (slug: string): Promise<PageContent> => {
  const response = await api.get<PageContent>(`/pages/${slug}/`);
  return response.data;
};

// ======================== Home Types ========================

export interface HomeContent {
  id: number;
  name: string;
  is_active: boolean;
  html: string;
  css: string;
  dynamic_config: Record<string, unknown>;
  status?: 'draft' | 'review' | 'published';
  published: boolean;
  created_at: string;
  updated_at: string;
}

export const fetchHomeContent = async (): Promise<HomeContent> => {
  const response = await api.get<HomeContent>('/pages/home/');
  return response.data;
};

// ======================== Google Sheets ========================

export interface GoogleSheetDataResponse {
  sheet_id: string;
  sheet_name: string;
  headers: string[];
  rows: string[][];
}

export const fetchGoogleSheetData = async (sheetId: string): Promise<GoogleSheetDataResponse> => {
  const response = await api.get<GoogleSheetDataResponse>(`/pages/google-sheets/${sheetId}/`);
  return response.data;
};
