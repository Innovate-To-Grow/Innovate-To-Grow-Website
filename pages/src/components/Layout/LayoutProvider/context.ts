import { createContext, useContext } from 'react';
import type { FooterContentResponse, Menu } from '../../../services/api';

export type LayoutLoadState = 'loading' | 'ready' | 'error';

export interface LayoutContextValue {
  state: LayoutLoadState;
  menus: Menu[];
  footer: FooterContentResponse | null;
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
  return {
    menu: menus.length > 0 ? menus[0] : null,
    state,
    error,
  };
};

export const useFooter = (): { footer: FooterContentResponse | null; state: LayoutLoadState; error: string | null } => {
  const { footer, state, error } = useLayout();
  return { footer, state, error };
};


