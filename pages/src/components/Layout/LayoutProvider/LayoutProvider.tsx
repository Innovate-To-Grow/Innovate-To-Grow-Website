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
} from '../../../services/api';
import { LayoutContext, type LayoutContextValue, type LayoutLoadState } from './context';

interface LayoutProviderProps {
  children: ReactNode;
}

interface RefreshLayoutOptions {
  force?: boolean;
}

const LAYOUT_REVALIDATE_MS = 60_000;

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
  const lastLoadedAtRef = useRef(0);
  const inFlightRef = useRef<Promise<void> | null>(null);
  const isUnmountedRef = useRef(false);

  const refreshLayout = useEffectEvent(async ({force = false}: RefreshLayoutOptions = {}) => {
    const now = Date.now();
    const isStale = !lastLoadedAtRef.current || now - lastLoadedAtRef.current >= LAYOUT_REVALIDATE_MS;

    if (!force && !isStale) {
      return;
    }

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

        lastLoadedAtRef.current = Date.now();
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
    void refreshLayout({force: true});

    const handleFocus = () => {
      void refreshLayout({force: true});
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void refreshLayout({force: true});
      }
    };

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void refreshLayout();
      }
    }, LAYOUT_REVALIDATE_MS);

    window.addEventListener('focus', handleFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      isUnmountedRef.current = true;
      window.clearInterval(intervalId);
      window.removeEventListener('focus', handleFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  const value: LayoutContextValue = useMemo(() => ({
    state,
    menus: layoutData?.menus ?? [],
    footer: layoutData?.footer ?? null,
    homepage_route: layoutData?.homepage_route,
    sheets_data: layoutData?.sheets_data,
    error,
  }), [state, layoutData, error]);

  return (
    <LayoutContext.Provider value={value}>
      {children}
    </LayoutContext.Provider>
  );
};
