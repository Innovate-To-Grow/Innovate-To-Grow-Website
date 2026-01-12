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

// ======================== Signup Types ========================

export interface SignupFormData {
  first_name: string;
  last_name: string;
  primary_email: string;
  confirm_primary_email: string;
  subscribe_primary_email: boolean;
  secondary_email?: string;
  confirm_secondary_email?: string;
  subscribe_secondary_email?: boolean;
  phone_number?: string;
  confirm_phone_number?: string;
  subscribe_phone?: boolean;
}

export interface SignupResponse {
  success: boolean;
  message: string;
  member_id: number;
  member_uuid: string;
  username: string;
}

export interface EmailVerificationData {
  token: string;
}

export interface EmailVerificationResponse {
  success: boolean;
  message: string;
  email: string;
}

export const signup = async (data: SignupFormData): Promise<SignupResponse> => {
  const response = await api.post<SignupResponse>('/authn/signup/', data);
  return response.data;
};

export const verifyEmail = async (data: EmailVerificationData): Promise<EmailVerificationResponse> => {
  const response = await api.post<EmailVerificationResponse>('/authn/signup/verify/', data);
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

// ======================== Site Settings Types ========================

export interface SiteSettings {
  id: number;
  home_page_mode: 'pre_event' | 'during_semester' | 'event';
  created_at: string;
  updated_at: string;
}

export const fetchSiteSettings = async (): Promise<SiteSettings> => {
  const response = await api.get<SiteSettings>('/pages/site-settings/');
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
  abstract: string | null;
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
  slug: string;
  is_live: boolean;
  programs: Program[];
  track_winners: TrackWinner[];
  special_awards: string[];
  created_at: string;
  updated_at: string;
}

export interface PastEventListItem {
  slug: string;
  event_name: string;
  event_date: string; // ISO date string
}

export const fetchEvent = async (): Promise<EventData> => {
  const response = await api.get<EventData>('/events/');
  return response.data;
};

export const fetchArchivedEvent = async (slug: string): Promise<EventData> => {
  const response = await api.get<EventData>(`/events/archive/${slug}/`);
  return response.data;
};

export const fetchPastEventsList = async (): Promise<PastEventListItem[]> => {
  const response = await api.get<PastEventListItem[]>('/events/past-events-list/');
  return response.data;
};

// ======================== Past Projects Types ========================

export interface PastProject {
  'Year-Semester': string;
  'Class': string;
  'Team#': string;
  'Team Name': string;
  'Project Title': string;
  'Organization': string;
  'Industry': string;
  'Abstract': string;
  'Student Names': string;
}

export interface SharedProjectURLRequest {
  team_names: string[];
  team_numbers: string[];
  project_keys?: string[]; // Optional: unique project identifiers for precise matching
}

export interface SharedProjectURLResponse {
  uuid: string;
  url: string;
}

export interface SharedProjectURLData {
  uuid: string;
  team_names: string[];
  team_numbers: string[];
  project_keys?: string[];
  created_at: string;
  expires_at: string | null;
}

// ======================== Past Projects API ========================

export const fetchPastProjects = async (): Promise<PastProject[]> => {
  const response = await api.get<PastProject[]>('/pages/past-projects/');
  return response.data;
};

export const createSharedURL = async (
  data: SharedProjectURLRequest
): Promise<SharedProjectURLResponse> => {
  const response = await api.post<SharedProjectURLResponse>(
    '/pages/past-projects/share/',
    data
  );
  return response.data;
};

export const fetchSharedURL = async (
  uuid: string
): Promise<SharedProjectURLData> => {
  const response = await api.get<SharedProjectURLData>(
    `/pages/past-projects/shared/${uuid}/`
  );
  return response.data;
};

export default api;
