import axios from 'axios';

// In development, Vite proxy will handle this
// In production, you may need to set this to your backend URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ======================== Page Types ========================

export interface PageContent {
  id: number;
  title: string;
  slug: string;
  page_type: 'page' | 'external';
  page_body: string | null;
  external_url: string | null;
  meta_title: string;
  meta_description: string;
  meta_keywords: string;
  og_image: string | null;
  canonical_url: string | null;
  meta_robots: string;
  template_name: string;
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
  body: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const fetchHomeContent = async (): Promise<HomeContent> => {
  const response = await api.get<HomeContent>('/pages/home/');
  return response.data;
};

// ======================== Footer ========================

export interface FooterLink {
  label: string;
  href: string;
  target?: string | null;
  rel?: string | null;
}

export interface FooterCTAButton {
  label: string;
  href: string;
  style?: 'blue' | 'gold';
}

export interface FooterColumn {
  title?: string;
  body_html?: string | null;
  links?: FooterLink[];
}

export interface FooterSocialLink {
  href: string;
  icon_class: string;
  aria_label?: string | null;
  target?: string | null;
  rel?: string | null;
}

export interface FooterContentData {
  cta_buttons?: FooterCTAButton[];
  contact_html?: string | null;
  columns?: FooterColumn[];
  social_links?: FooterSocialLink[];
  copyright?: string | null;
  footer_links?: FooterLink[];
}

export interface FooterContentResponse {
  id: number;
  name: string;
  slug: string;
  content: FooterContentData;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const fetchFooterContent = async (): Promise<FooterContentResponse> => {
  const response = await api.get<FooterContentResponse>('/layout/footer/');
  return response.data;
};

// ======================== Health Check ========================

export interface HealthCheckResponse {
  status: 'ok' | 'error';
  database: string;
}

export const checkHealth = async (): Promise<boolean> => {
  try {
    const response = await api.get<HealthCheckResponse>('/health/', {
      timeout: 5000, // 5 second timeout
    });
    return response.data.status === 'ok';
  } catch {
    return false;
  }
};

export default api;
