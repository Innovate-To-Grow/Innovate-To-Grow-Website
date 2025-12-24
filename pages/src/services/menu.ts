import api from './api';

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

export interface MenuResponse {
  menus: Menu[];
}

export const fetchMenus = async (): Promise<Menu[]> => {
  try {
    const response = await api.get<MenuResponse>('/layout/menus/');
    return response.data.menus;
  } catch (error) {
    console.error('Error fetching menus:', error);
    return [];
  }
};

// Cache menu data to reduce API calls
let menuCache: Menu[] | null = null;

export const getCachedMenus = async (): Promise<Menu[]> => {
  if (menuCache === null) {
    menuCache = await fetchMenus();
  }
  return menuCache;
};

export const clearMenuCache = () => {
  menuCache = null;
};
