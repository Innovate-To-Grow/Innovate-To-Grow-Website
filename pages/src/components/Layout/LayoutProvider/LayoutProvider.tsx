import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import {
  fetchLayoutData,
  type LayoutData,
  type Menu,
  type FooterContentResponse,
} from '../../../services/api';

type LoadState = 'loading' | 'ready' | 'error';

interface LayoutContextValue {
  state: LoadState;
  menus: Menu[];
  footer: FooterContentResponse | null;
  error: string | null;
}

const defaultContext: LayoutContextValue = {
  state: 'loading',
  menus: [],
  footer: null,
  error: null,
};

const LayoutContext = createContext<LayoutContextValue>(defaultContext);

export const useLayout = () => {
  const context = useContext(LayoutContext);
  if (!context) {
    throw new Error('useLayout must be used within a LayoutProvider');
  }
  return context;
};

export const useMenu = (): { menu: Menu | null; state: LoadState; error: string | null } => {
  const { menus, state, error } = useLayout();
  return {
    menu: menus.length > 0 ? menus[0] : null,
    state,
    error,
  };
};

export const useFooter = (): { footer: FooterContentResponse | null; state: LoadState; error: string | null } => {
  const { footer, state, error } = useLayout();
  return { footer, state, error };
};

interface LayoutProviderProps {
  children: ReactNode;
}

export const LayoutProvider = ({ children }: LayoutProviderProps) => {
  const [layoutData, setLayoutData] = useState<LayoutData | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadLayout = async () => {
      try {
        const data = await fetchLayoutData();
        setLayoutData(data);
        setState('ready');
      } catch (err) {
        console.error('Failed to load layout data', err);
        setError('Layout data is currently unavailable.');
        setState('error');
      }
    };

    loadLayout();
  }, []);

  const value: LayoutContextValue = {
    state,
    menus: layoutData?.menus ?? [],
    footer: layoutData?.footer ?? null,
    error,
  };

  return (
    <LayoutContext.Provider value={value}>
      {children}
    </LayoutContext.Provider>
  );
};

