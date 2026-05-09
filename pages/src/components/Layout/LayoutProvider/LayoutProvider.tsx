import {
  startTransition,
  useEffect,
  useEffectEvent,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  fetchLayoutData,
  readLayoutCache,
  writeLayoutCache,
  type LayoutData,
} from '../../../features/layout/api';
import { LayoutContext, type LayoutContextValue, type LayoutLoadState } from './context';

interface LayoutProviderProps {
  children: ReactNode;
}

// Note: CSS (design tokens + stylesheets) is delivered by the render-blocking
// <link rel="stylesheet" href="/api/layout/styles.css"> in index.html.
// React only handles menus/footer data — it no longer injects CSS into the DOM.

function getInitialLayoutFromStorage(): { data: LayoutData | null; state: LayoutLoadState } {
  const cached = readLayoutCache();
  return cached
    ? { data: cached, state: 'ready' as const }
    : { data: null, state: 'loading' as const };
}

export const LayoutProvider = ({ children }: LayoutProviderProps) => {
  const initialLayout = useMemo(() => getInitialLayoutFromStorage(), []);
  const [layoutData, setLayoutData] = useState<LayoutData | null>(() => initialLayout.data);
  const [state, setState] = useState<LayoutLoadState>(() => initialLayout.state);
  const [error, setError] = useState<string | null>(null);
  const inFlightRef = useRef<Promise<void> | null>(null);
  const isUnmountedRef = useRef(false);

  const loadLayout = useEffectEvent(async () => {
    if (inFlightRef.current) {
      await inFlightRef.current;
      return;
    }

    if (!layoutData) {
      startTransition(() => {
        setState('loading');
        setError(null);
      });
    }

    const request = fetchLayoutData()
      .then((data) => {
        if (isUnmountedRef.current) {
          return;
        }

        writeLayoutCache(data);

        startTransition(() => {
          setLayoutData(data);
          setError(null);
          setState('ready');
        });
      })
      .catch((err) => {
        console.error('Failed to load layout data', err);

        if (isUnmountedRef.current || layoutData) {
          return;
        }

        startTransition(() => {
          setError('Layout data is currently unavailable.');
          setState('error');
        });
      })
      .finally(() => {
        inFlightRef.current = null;
      });

    inFlightRef.current = request;
    await request;
  });

  useEffect(() => {
    isUnmountedRef.current = false;
    void loadLayout();
    return () => {
      isUnmountedRef.current = true;
    };
  }, []);

  const value: LayoutContextValue = useMemo(() => ({
    state,
    menus: layoutData?.menus ?? [],
    footer: layoutData?.footer ?? null,
    homepage_route: layoutData?.homepage_route,
    error,
  }), [state, layoutData, error]);

  return (
    <LayoutContext.Provider value={value}>
      {children}
    </LayoutContext.Provider>
  );
};
