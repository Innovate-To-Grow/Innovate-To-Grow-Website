import api from './client';

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
