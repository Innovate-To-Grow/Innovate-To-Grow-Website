import api from './client';

// ======================== Page Types ========================

export interface PageContent {
  id: number;
  title: string;
  slug: string;
  page_type?: 'page' | 'external';
  page_body?: string | null;
  external_url?: string | null;
  meta_title: string;
  meta_description: string;
  meta_keywords: string;
  og_image: string | null;
  canonical_url: string | null;
  meta_robots: string;
  template_name: string;
  status?: 'draft' | 'review' | 'published';
  published: boolean;
  components?: PageComponent[];
  created_at: string;
  updated_at: string;
}

export const fetchPageContent = async (slug: string): Promise<PageContent> => {
  const response = await api.get<PageContent>(`/pages/${slug}/`);
  return response.data;
};

// ======================== Page Component Types ========================

export interface PageComponent {
  id: number;
  name: string;
  component_type: 'html' | 'markdown' | 'form' | 'table' | 'google_sheet';
  order: number;
  is_enabled: boolean;
  html_content: string;
  css_file: string | null;
  css_code: string;
  js_code: string;
  config: Record<string, unknown> | null;
  google_sheet: string | null;
  google_sheet_style: 'default' | 'striped' | 'bordered' | 'compact';
  created_at: string;
  updated_at: string;
}

export interface GoogleSheetDataResponse {
  sheet_id: string;
  sheet_name: string;
  headers: string[];
  rows: string[][];
}

// ======================== Home Types ========================

export interface HomeContent {
  id: number;
  name: string;
  body?: string;
  is_active: boolean;
  status?: 'draft' | 'review' | 'published';
  published: boolean;
  components?: PageComponent[];
  created_at: string;
  updated_at: string;
}

export const fetchHomeContent = async (): Promise<HomeContent> => {
  const response = await api.get<HomeContent>('/pages/home/');
  return response.data;
};

export const fetchGoogleSheetData = async (sheetId: string): Promise<GoogleSheetDataResponse> => {
  const response = await api.get<GoogleSheetDataResponse>(`/pages/google-sheets/${sheetId}/`);
  return response.data;
};
