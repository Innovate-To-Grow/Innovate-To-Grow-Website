import { useEffect, useReducer } from 'react';
import { useLocation } from 'react-router-dom';

import { MiniAppRenderer } from '../../components/MiniApp';
import { CMSPageComponent } from '../../components/CMS';
import { api } from '../../shared/api/client';

interface MiniAppMeta {
  slug: string;
  title: string;
}

type State =
  | { status: 'resolving' }
  | { status: 'miniapp'; meta: MiniAppMeta }
  | { status: 'cms' };

type Action =
  | { type: 'reset' }
  | { type: 'resolved'; meta: MiniAppMeta }
  | { type: 'fallback' };

function reducer(_state: State, action: Action): State {
  switch (action.type) {
    case 'reset':
      return { status: 'resolving' };
    case 'resolved':
      return { status: 'miniapp', meta: action.meta };
    case 'fallback':
      return { status: 'cms' };
  }
}

export const MiniAppPage = () => {
  const location = useLocation();
  const urlPath = location.pathname;

  const [state, dispatch] = useReducer(reducer, { status: 'resolving' });

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: 'reset' });

    api
      .get('/miniapps/resolve/', { params: { path: urlPath } })
      .then((res) => {
        if (!cancelled) dispatch({ type: 'resolved', meta: res.data });
      })
      .catch(() => {
        if (!cancelled) dispatch({ type: 'fallback' });
      });

    return () => { cancelled = true; };
  }, [urlPath]);

  useEffect(() => {
    if (state.status === 'miniapp') {
      document.title = `${state.meta.title} | Innovate to Grow`;
    }
  }, [state]);

  if (state.status === 'miniapp') {
    return <MiniAppRenderer slug={state.meta.slug} path={urlPath} />;
  }

  if (state.status === 'cms') {
    return <CMSPageComponent />;
  }

  // Brief loading state while resolve completes (typically <100ms).
  // This prevents CMSPageComponent from flashing NotFoundPage for miniapp routes.
  return <div className="cms-page-loading" />;
};
