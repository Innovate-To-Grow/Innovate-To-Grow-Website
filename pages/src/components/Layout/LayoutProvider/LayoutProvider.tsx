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
  type DesignTokens,
} from '../../../services/api';
import { LayoutContext, type LayoutContextValue, type LayoutLoadState } from './context';

interface LayoutProviderProps {
  children: ReactNode;
}

/** Map design-token JSON groups to CSS custom-property prefixes. */
const GROUP_PREFIX: Record<string, string> = {
  colors: 'color',
  typography: '',
  typography_mobile: '',
  layout: '',
  borders: '',
  effects: '',
};

function applyDesignTokens(tokens: DesignTokens) {
  const root = document.documentElement;
  for (const [group, values] of Object.entries(tokens)) {
    const prefix = GROUP_PREFIX[group] ?? '';
    for (const [key, value] of Object.entries(values as Record<string, string>)) {
      const kebab = key.replace(/_/g, '-');
      const varName = prefix ? `--itg-${prefix}-${kebab}` : `--itg-${kebab}`;
      root.style.setProperty(varName, value);
    }
  }
}

function applyStylesheets(css: string) {
  let el = document.getElementById('itg-server-styles');
  if (!el) {
    el = document.createElement('style');
    el.id = 'itg-server-styles';
    document.head.appendChild(el);
  }
  el.textContent = css;
}

function getInitialLayoutFromStorage(): { data: LayoutData | null; state: LayoutLoadState } {
  const cached = readLayoutCache();
  return cached
    ? { data: cached, state: 'ready' as const }
    : { data: null, state: 'loading' as const };
}

export const LayoutProvider = ({ children }: LayoutProviderProps) => {
  const initialLayout = useMemo(() => {
    const result = getInitialLayoutFromStorage();
    // Apply cached styles immediately to avoid flash of unstyled content
    if (result.data?.design_tokens) {
      applyDesignTokens(result.data.design_tokens);
    }
    if (result.data?.stylesheets) {
      applyStylesheets(result.data.stylesheets);
    }
    return result;
  }, []);
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

        // Inject server-managed styles into the DOM
        if (data.design_tokens) {
          applyDesignTokens(data.design_tokens);
        }
        if (data.stylesheets) {
          applyStylesheets(data.stylesheets);
        }

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
