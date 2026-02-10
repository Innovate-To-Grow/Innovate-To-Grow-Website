import axios from 'axios';

// In development, Vite proxy will handle this
// In production, you may need to set this to your backend URL
// Default to /api so local dev can proxy backend requests without colliding
// with client-side routes like /pages/*
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

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
  component_type: 'html' | 'form' | 'google_sheet' | 'sheet';
  order: number;
  html_content: string;
  css_file: string | null;
  css_code: string;
  js_code: string;
  config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
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

// ======================== Menu Types ========================

export interface MenuItem {
  type: 'home' | 'page' | 'external';
  title: string;
  url: string;
  page_slug?: string;
  page_type?: string;
  icon?: string | null;
  open_in_new_tab: boolean;
  children: MenuItem[];
}

export interface Menu {
  id: number;
  name: string;
  display_name: string;
  description: string;
  items: MenuItem[];
  created_at: string;
  updated_at: string;
}

// ======================== Layout ========================

export interface LayoutData {
  menus: Menu[];
  footer: FooterContentResponse | null;
}

let layoutCache: Promise<LayoutData> | null = null;

export const fetchLayoutData = async (): Promise<LayoutData> => {
  if (layoutCache) {
    return layoutCache;
  }

  layoutCache = api.get<LayoutData>('/layout/').then(
    response => response.data,
    error => {
      layoutCache = null;
      throw error;
    }
  );
  return layoutCache;
};

export const clearLayoutCache = () => {
  layoutCache = null;
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

// ======================== Event Types ========================

export interface Presentation {
  order: number;
  team_id: string;
  team_name: string;
  project_title: string;
  organization: string;
}

export interface Track {
  track_name: string;
  room: string;
  start_time: string | null;
  presentations: Presentation[];
}

export interface Program {
  program_name: string;
  tracks: Track[];
}

export interface TrackWinner {
  track_name: string;
  winner_name: string;
}

export interface SpecialAward {
  program_name: string;
  award_winner: string;
}

export interface ExpoRow {
  time: string;
  room: string;
  description: string;
}

export interface ReceptionRow {
  time: string;
  room: string;
  description: string;
}

export interface EventData {
  event_uuid: string;
  event_name: string;
  event_date: string; // ISO date string
  event_time: string; // ISO time string
  upper_bullet_points: string[]; // Markdown strings
  lower_bullet_points: string[]; // Markdown strings
  expo_table: ExpoRow[];
  reception_table: ReceptionRow[];
  is_published: boolean;
  programs: Program[];
  track_winners: TrackWinner[];
  special_awards: SpecialAward[];
  created_at: string;
  updated_at: string;
}

export const fetchEvent = async (): Promise<EventData> => {
  const response = await api.get<EventData>('/events/');
  return response.data;
};

export default api;
