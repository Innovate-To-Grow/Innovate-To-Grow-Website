import { useEffect, useState, type ReactNode } from 'react';
import {
  fetchLayoutData,
  type LayoutData,
} from '../../../services/api';
import { LayoutContext, type LayoutContextValue, type LayoutLoadState } from './context';

interface LayoutProviderProps {
  children: ReactNode;
}

export const LayoutProvider = ({ children }: LayoutProviderProps) => {
  const [layoutData, setLayoutData] = useState<LayoutData | null>(null);
  const [state, setState] = useState<LayoutLoadState>('loading');
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

