import { useCallback, useEffect, useState } from 'react';
import { BlockRenderer } from './BlockRenderer';
import { cmsPageClassName } from './pageClassName';
import type { CMSBlock } from '@/features/cms/api';
import { useReportFrameHeight } from '@/hooks/useReportFrameHeight';
import {
  getExpectedPreviewNonce,
  getInitialReadyTargetOrigins,
  getTrustedReferrerOrigin,
  isTrustedParentOrigin,
  normalizeOrigin,
} from '@/lib/preview';

/**
 * Lightweight page rendered inside an iframe for per-block admin preview.
 * Receives block data via window.postMessage from the parent admin page.
 *
 * Message protocol:
 *   iframe URL: /_block-preview?nonce=<per-iframe random value>
 *   parent → iframe:
 *     { type: 'cms-block-preview', nonce, block: {...}, pageCssClass? }
 *   iframe → parent:
 *     { type: 'cms-block-preview-ready' | 'cms-block-preview-resize', nonce, ... }
 */

export const BlockPreviewPage = () => {
  const [block, setBlock] = useState<CMSBlock | null>(null);
  const [pageCssClass, setPageCssClass] = useState('');
  const [trustedParentOrigin, setTrustedParentOrigin] = useState(getTrustedReferrerOrigin);
  const [expectedNonce] = useState(getExpectedPreviewNonce);

  const handleMessage = useCallback((event: MessageEvent) => {
    if (!expectedNonce) return;
    if (event.source !== window.parent) return;
    const normalizedOrigin = normalizeOrigin(event.origin);
    if (!normalizedOrigin || !isTrustedParentOrigin(normalizedOrigin)) return;
    const msg = event.data;
    if (
      !msg ||
      msg.type !== 'cms-block-preview' ||
      msg.nonce !== expectedNonce
    ) {
      return;
    }
    setTrustedParentOrigin(normalizedOrigin);
    if (msg.block) {
      setBlock({
        block_type: msg.block.block_type,
        sort_order: msg.block.sort_order ?? 0,
        data: msg.block.data ?? {},
      });
    }
    if (msg.pageCssClass !== undefined) {
      setPageCssClass(typeof msg.pageCssClass === 'string' ? msg.pageCssClass : '');
    }
  }, [expectedNonce]);

  useEffect(() => {
    window.addEventListener('message', handleMessage);
    if (expectedNonce && window.parent !== window) {
      for (const origin of getInitialReadyTargetOrigins()) {
        window.parent.postMessage(
          {type: 'cms-block-preview-ready', nonce: expectedNonce},
          origin,
        );
      }
    }
    return () => window.removeEventListener('message', handleMessage);
  }, [expectedNonce, handleMessage]);

  useReportFrameHeight('cms-block-preview-resize', expectedNonce, trustedParentOrigin, block, pageCssClass);

  if (!block) {
    return (
      <p className="cms-block-preview-waiting" role="status">
        Waiting for block data...
      </p>
    );
  }

  return (
    <div className={cmsPageClassName(pageCssClass)}>
      <BlockRenderer blocks={[block]} previewMode />
    </div>
  );
};
