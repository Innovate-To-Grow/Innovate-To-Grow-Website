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

const ALLOWED_PARENT_ORIGINS = new Set<string>([
  normalizeOrigin(window.location.origin),
  ...parseAllowedOrigins(import.meta.env.VITE_ADMIN_ORIGIN),
]);

function isTrustedParentOrigin(origin: string): boolean {
  const normalizedOrigin = normalizeOrigin(origin);
  if (!normalizedOrigin) return false;
  return ALLOWED_PARENT_ORIGINS.has(normalizedOrigin) || isTrustedDevLoopbackOrigin(normalizedOrigin);
}

export const BlockPreviewPage = () => {
  const [block, setBlock] = useState<CMSBlock | null>(null);
  const [pageCssClass, setPageCssClass] = useState('');

  const handleMessage = useCallback((event: MessageEvent) => {
    if (!isTrustedParentOrigin(event.origin)) return;
    const msg = event.data;
    if (!msg || msg.type !== 'cms-block-preview') return;
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
      window.parent.postMessage({ type: 'cms-block-preview-ready' }, '*');
    }
    return () => window.removeEventListener('message', handleMessage);
  }, [handleMessage]);

  if (!block) {
    return (
      <div style={{ padding: '24px', color: '#999', fontStyle: 'italic', textAlign: 'center' }}>
        Waiting for block data...
      </div>
    );
  }

  return (
    <div className={pageCssClass || 'cms-page'}>
      <BlockRenderer blocks={[block]} />
    </div>
  );
};
