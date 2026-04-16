import api from '../../shared/api/client';

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
  id: string;
  name: string;
  slug: string;
  content: FooterContentData;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ======================== Menu Types ========================

export interface MenuItem {
  type: 'external' | 'app' | 'home';
  title: string;
  url: string;
  icon?: string | null;
  open_in_new_tab: boolean;
  children: MenuItem[];
}

export interface Menu {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  items: MenuItem[];
  created_at: string;
  updated_at: string;
}

export interface DesignTokens {
  colors: Record<string, string>;
  typography: Record<string, string>;
  typography_mobile: Record<string, string>;
  layout: Record<string, string>;
  borders: Record<string, string>;
  effects: Record<string, string>;
}

export interface LayoutData {
  menus: Menu[];
  footer: FooterContentResponse | null;
  homepage_route?: string;
  design_tokens?: DesignTokens;
  stylesheets?: string;
}

/** Bump when cached JSON shape is incompatible. */
export const LAYOUT_CACHE_VERSION = 2;

const LAYOUT_CACHE_STORAGE_KEY = 'itg-layout-v2';

interface StoredLayoutPayload {
  v: number;
  data: LayoutData;
}

function isLayoutDataShape(value: unknown): value is LayoutData {
  if (!value || typeof value !== 'object') return false;
  const o = value as Record<string, unknown>;
  return Array.isArray(o.menus);
}

export function readLayoutCache(): LayoutData | null {
  if (typeof window === 'undefined' || !window.sessionStorage) {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(LAYOUT_CACHE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object') return null;
    const payload = parsed as StoredLayoutPayload;
    if (payload.v !== LAYOUT_CACHE_VERSION || !isLayoutDataShape(payload.data)) {
      return null;
    }
    return payload.data;
  } catch {
    return null;
  }
}

export function writeLayoutCache(data: LayoutData): void {
  if (typeof window === 'undefined' || !window.sessionStorage) {
    return;
  }
  try {
    const payload: StoredLayoutPayload = { v: LAYOUT_CACHE_VERSION, data };
    window.sessionStorage.setItem(LAYOUT_CACHE_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // QuotaExceededError or private mode — ignore
  }
}

/** In-flight dedupe: multiple LayoutProvider roots share one network request. */
let layoutFetchInFlight: Promise<LayoutData> | null = null;

export const fetchLayoutData = async (): Promise<LayoutData> => {
  if (!layoutFetchInFlight) {
    layoutFetchInFlight = api
      .get<LayoutData>('/layout/')
      .then((response) => response.data)
      .finally(() => {
        layoutFetchInFlight = null;
      });
  }
  return layoutFetchInFlight;
};

export const clearLayoutCache = (): void => {
  if (typeof window === 'undefined' || !window.sessionStorage) {
    return;
  }
  try {
    window.sessionStorage.removeItem(LAYOUT_CACHE_STORAGE_KEY);
  } catch {
    // ignore
  }
};
