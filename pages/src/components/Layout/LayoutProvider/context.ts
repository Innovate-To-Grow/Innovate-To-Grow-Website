import { createContext, useContext } from 'react';
import type { FooterContentResponse, Menu } from '../../../services/api';
import type { HomepageMode } from '../../../services/api/layout';
import type { SheetsDataResponse } from '../../../services/api/sheets';

export type LayoutLoadState = 'loading' | 'ready' | 'error';

export interface LayoutContextValue {
  state: LayoutLoadState;
  menus: Menu[];
  footer: FooterContentResponse | null;
  homepage_mode?: HomepageMode;
  homepage_route?: string;
  sheets_data?: Record<string, SheetsDataResponse>;
  error: string | null;
}

export const defaultLayoutContext: LayoutContextValue = {
  state: 'loading',
  menus: [],
  footer: null,
  error: null,
};

export const LayoutContext = createContext<LayoutContextValue>(defaultLayoutContext);

export const useLayout = () => useContext(LayoutContext);

export const useMenu = (): { menu: Menu | null; state: LayoutLoadState; error: string | null } => {
  const { menus, state, error } = useLayout();

  // Prioritize 'main-nav' or 'main_nav', then fall back to 'main', then first available
  const menu = menus.find(m => m.name === 'main-nav') ||
               menus.find(m => m.name === 'main_nav') ||
               menus.find(m => m.name === 'main') ||
               (menus.length > 0 ? menus[0] : null);

  return {
    menu,
    state,
    error,
  };
};

export const useFooter = (): { footer: FooterContentResponse | null; state: LayoutLoadState; error: string | null } => {
  const { footer, state, error } = useLayout();
  return { footer, state, error };
};
