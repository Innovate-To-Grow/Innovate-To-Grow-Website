import { useCallback, useEffect, useState } from 'react';
import { BlockRenderer } from './BlockRenderer';
import type { CMSBlock } from '../../features/cms/api';

/**
 * Lightweight page rendered inside an iframe for per-block admin preview.
 * Receives block data via window.postMessage from the parent admin page.
 *
 * Message protocol:
 *   { type: 'cms-block-preview', block: { block_type, sort_order, data }, pageCssClass? }
 */

// postMessage origin allowlist, frozen at module load.
//
// Same-origin is always trusted (covers dev via the Vite proxy and prod
// deployments where admin and SPA share a host). Split frontend/backend
// setups run the Django admin on a different origin — the admin embeds this
// iframe using the configured FRONTEND_URL, so messages arrive with the
// admin's origin as event.origin. `VITE_ADMIN_ORIGIN` lists those trusted
// parent origins (comma-separated if there are multiple), e.g.
// "https://admin.example.com".
function parseAllowedOrigins(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((o) => normalizeOrigin(o))
    .filter(Boolean);
}

function normalizeOrigin(raw: string): string {
  try {
    const url = new URL(String(raw || '').trim());
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
    return url.origin.replace(/\/+$/, '');
  } catch {
    return '';
  }
}

function isLoopbackHost(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
}

function isTrustedDevLoopbackOrigin(origin: string): boolean {
  if (!import.meta.env.DEV) return false;

  try {
    const iframeOrigin = new URL(window.location.origin);
    const parentOrigin = new URL(origin);
    return (
      iframeOrigin.protocol === 'http:' &&
      parentOrigin.protocol === 'http:' &&
      isLoopbackHost(iframeOrigin.hostname) &&
      isLoopbackHost(parentOrigin.hostname)
    );
  } catch {
    return false;
  }
}

const SAME_ORIGIN = normalizeOrigin(window.location.origin);
const CONFIGURED_PARENT_ORIGINS = parseAllowedOrigins(import.meta.env.VITE_ADMIN_ORIGIN);
const ALLOWED_PARENT_ORIGINS = new Set<string>([
  SAME_ORIGIN,
  ...CONFIGURED_PARENT_ORIGINS,
]);

function isTrustedParentOrigin(origin: string): boolean {
  const normalizedOrigin = normalizeOrigin(origin);
  if (!normalizedOrigin) return false;
  return ALLOWED_PARENT_ORIGINS.has(normalizedOrigin) || isTrustedDevLoopbackOrigin(normalizedOrigin);
}

function getTrustedReferrerOrigin(): string {
  const referrerOrigin = normalizeOrigin(document.referrer);
  return referrerOrigin && isTrustedParentOrigin(referrerOrigin) ? referrerOrigin : '';
}

function getInitialReadyTargetOrigin(): string {
  const referrerOrigin = getTrustedReferrerOrigin();
  if (referrerOrigin) return referrerOrigin;
  if (CONFIGURED_PARENT_ORIGINS.length === 1) return CONFIGURED_PARENT_ORIGINS[0];
  return SAME_ORIGIN || window.location.origin;
}

export const BlockPreviewPage = () => {
  const [block, setBlock] = useState<CMSBlock | null>(null);
  const [pageCssClass, setPageCssClass] = useState('');
  const [trustedParentOrigin, setTrustedParentOrigin] = useState(getTrustedReferrerOrigin);

  const handleMessage = useCallback((event: MessageEvent) => {
    const normalizedOrigin = normalizeOrigin(event.origin);
    if (!normalizedOrigin || !isTrustedParentOrigin(normalizedOrigin)) return;
    const msg = event.data;
    if (!msg || msg.type !== 'cms-block-preview') return;
    setTrustedParentOrigin(normalizedOrigin);
    if (msg.block) {
      setBlock({
        block_type: msg.block.block_type,
        sort_order: msg.block.sort_order ?? 0,
        data: msg.block.data ?? {},
      });
    }
    if (msg.pageCssClass !== undefined) {
      setPageCssClass(msg.pageCssClass || '');
    }
  }, []);

  useEffect(() => {
    window.addEventListener('message', handleMessage);
    // Signal parent that the iframe is ready to receive data
    if (window.parent !== window) {
      window.parent.postMessage({ type: 'cms-block-preview-ready' }, getInitialReadyTargetOrigin());
    }
    return () => window.removeEventListener('message', handleMessage);
  }, [handleMessage]);

  useEffect(() => {
    if (!block || !trustedParentOrigin || window.parent === window) return;

    const reportHeight = () => {
      const height = Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0,
        document.documentElement.offsetHeight,
        document.body ? document.body.offsetHeight : 0,
      );
      if (height > 0) {
        window.parent.postMessage({ type: 'cms-block-preview-resize', height }, trustedParentOrigin);
      }
    };

    reportHeight();
    const timers = [
      window.setTimeout(reportHeight, 100),
      window.setTimeout(reportHeight, 500),
      window.setTimeout(reportHeight, 1500),
    ];
    const resizeObserver =
      typeof ResizeObserver !== 'undefined' ? new ResizeObserver(reportHeight) : null;
    if (resizeObserver) {
      resizeObserver.observe(document.documentElement);
      if (document.body) resizeObserver.observe(document.body);
    }
    window.addEventListener('load', reportHeight);
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      resizeObserver?.disconnect();
      window.removeEventListener('load', reportHeight);
    };
  }, [block, pageCssClass, trustedParentOrigin]);

  if (!block) {
    return (
      <div style={{ padding: '24px', color: '#999', fontStyle: 'italic', textAlign: 'center' }}>
        Waiting for block data...
      </div>
    );
  }

  return (
    <div className={pageCssClass || 'cms-page'}>
      <BlockRenderer blocks={[block]} previewMode />
    </div>
  );
};
