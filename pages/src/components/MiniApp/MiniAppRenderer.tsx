import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../Auth';
import { fetchMiniAppCode } from '../../features/miniapps/api';
import { createPostMessageBridge } from './PostMessageBridge';

interface MiniAppRendererProps {
  slug: string;
  path?: string;
}

type LoadState =
  | { status: 'loading'; html: null }
  | { status: 'loaded'; html: string }
  | { status: 'error'; error: string; html: null };

type LoadAction =
  | { type: 'reset' }
  | { type: 'loaded'; html: string }
  | { type: 'error'; error: string };

function loadReducer(_state: LoadState, action: LoadAction): LoadState {
  switch (action.type) {
    case 'reset':
      return { status: 'loading', html: null };
    case 'loaded':
      return { status: 'loaded', html: action.html };
    case 'error':
      return { status: 'error', error: action.error, html: null };
  }
}

export const MiniAppRenderer = ({ slug, path }: MiniAppRendererProps) => {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [state, dispatch] = useReducer(loadReducer, { status: 'loading', html: null });
  const [height, setHeight] = useState(400);
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: 'reset' });

    fetchMiniAppCode(slug, path)
      .then((code) => {
        if (!cancelled) dispatch({ type: 'loaded', html: code });
      })
      .catch((err) => {
        if (!cancelled) {
          const errorType = err.response?.status === 404 ? 'not_found' : 'load_error';
          dispatch({ type: 'error', error: errorType });
        }
      });

    return () => { cancelled = true; };
  }, [slug, path]);

  const getUser = useCallback(() => {
    if (!isAuthenticated || !user) return null;
    return {
      id: user.member_uuid || '',
      email: user.email || '',
      name: user.email || '',
    };
  }, [isAuthenticated, user]);

  const handleResize = useCallback((h: number) => {
    setHeight(Math.max(200, Math.min(h, 5000)));
  }, []);

  useEffect(() => {
    if (state.status !== 'loaded') return;

    const cleanup = createPostMessageBridge(slug, iframeRef, {
      onResize: handleResize,
      onNavigate: (path) => {
        if (path.startsWith('/') && !path.startsWith('//')) {
          navigate(path);
        }
      },
      getUser,
    });

    return cleanup;
  }, [state.status, slug, navigate, getUser, handleResize]);

  if (state.status === 'loading') {
    return <div className="miniapp-loading" aria-label="Loading" role="status" />;
  }

  if (state.status === 'error') {
    if (state.error === 'not_found') return null;
    return (
      <div className="miniapp-error">
        <p>Something went wrong loading this app.</p>
      </div>
    );
  }

  return (
    <iframe
      ref={iframeRef}
      className="miniapp-iframe"
      sandbox="allow-scripts allow-forms allow-popups"
      srcDoc={state.html}
      style={{
        width: '100%',
        height: `${height}px`,
        border: 'none',
        display: 'block',
      }}
      title={`Mini App: ${slug}`}
    />
  );
};
