import {useCallback, useEffect, useMemo, useState} from 'react';
import type {FooterContentData} from '@/features/layout/api';
import {useReportFrameHeight} from '@/hooks/useReportFrameHeight';
import {
  getExpectedPreviewNonce,
  getInitialReadyTargetOrigins,
  getTrustedReferrerOrigin,
  isTrustedParentOrigin,
  normalizeOrigin,
} from '@/lib/preview';
import {Footer} from '../Footer/Footer';
import {LayoutContext, type LayoutContextValue} from '../LayoutProvider/context';

/**
 * The admin footer editor's preview: the real Footer, styled by the bundle, rendering the content
 * the editor posts. Same trust rules as /_block-preview (lib/preview).
 *
 * Message protocol:
 *   iframe URL: /_footer-preview?nonce=<per-iframe random value>
 *   parent → iframe: { type: 'cms-footer-preview', nonce, content: {...} }
 *   iframe → parent: { type: 'cms-footer-preview-ready' | 'cms-footer-preview-resize', nonce, height? }
 */
export const FooterPreviewPage = () => {
  const [content, setContent] = useState<FooterContentData | null>(null);
  const [trustedParentOrigin, setTrustedParentOrigin] = useState(getTrustedReferrerOrigin);
  const [expectedNonce] = useState(getExpectedPreviewNonce);

  const handleMessage = useCallback((event: MessageEvent) => {
    if (!expectedNonce) return;
    if (event.source !== window.parent) return;
    const normalizedOrigin = normalizeOrigin(event.origin);
    if (!normalizedOrigin || !isTrustedParentOrigin(normalizedOrigin)) return;
    const msg = event.data;
    if (!msg || msg.type !== 'cms-footer-preview' || msg.nonce !== expectedNonce) return;
    if (!msg.content || typeof msg.content !== 'object' || Array.isArray(msg.content)) return;
    setTrustedParentOrigin(normalizedOrigin);
    setContent(msg.content as FooterContentData);
  }, [expectedNonce]);

  useEffect(() => {
    window.addEventListener('message', handleMessage);
    if (expectedNonce && window.parent !== window) {
      for (const origin of getInitialReadyTargetOrigins()) {
        window.parent.postMessage({type: 'cms-footer-preview-ready', nonce: expectedNonce}, origin);
      }
    }
    return () => window.removeEventListener('message', handleMessage);
  }, [expectedNonce, handleMessage]);

  useReportFrameHeight('cms-footer-preview-resize', expectedNonce, trustedParentOrigin, content);

  const layout: LayoutContextValue | null = useMemo(
    () =>
      content && {
        state: 'ready',
        menus: [],
        footer: {
          id: 'preview',
          name: 'Preview',
          slug: 'preview',
          content,
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        error: null,
      },
    [content],
  );

  if (!layout) {
    return (
      <p className="cms-block-preview-waiting" role="status">
        Waiting for footer data...
      </p>
    );
  }

  return (
    <LayoutContext.Provider value={layout}>
      <Footer />
    </LayoutContext.Provider>
  );
};
