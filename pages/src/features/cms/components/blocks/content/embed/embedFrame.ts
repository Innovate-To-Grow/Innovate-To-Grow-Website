import { useEffect, useState, type CSSProperties, type RefObject } from 'react';

// A cooperating embedded page posts its content height so we can grow the iframe to fit.
// The same contract serves third-party embeds and same-origin embed widgets.
const RESIZE_MESSAGE_TYPE = 'i2g-embed-resize';

/** "16:9" as a CSS aspect-ratio ("16 / 9"), or null when absent or malformed. */
export function parseAspectRatio(value?: string): string | null {
  if (!value) return null;
  const match = /^(\d+):(\d+)$/.exec(value);
  if (!match) return null;
  const w = Number(match[1]);
  const h = Number(match[2]);
  if (!w || !h) return null;
  return `${w} / ${h}`;
}

/** A positive pixel height from the block, or null when it sets none (or an unusable one). */
export function parseFixedHeight(height: number | string | undefined | null): number | null {
  if (height === undefined || height === null || String(height).trim() === '') return null;
  const value = Number(height);
  return Number.isFinite(value) && value > 0 ? value : null;
}

/** A fixed height, else an aspect ratio, else the reported height, else the placeholder. */
export function frameStyleFor(
  fixedHeight: number | null,
  aspect: string | null,
  autoHeight: number | null,
  placeholder: CSSProperties,
): CSSProperties {
  const base: CSSProperties = { position: 'relative', width: '100%', overflow: 'hidden' };
  if (fixedHeight !== null) return { ...base, height: `${fixedHeight}px` };
  if (aspect) return { ...base, aspectRatio: aspect };
  if (autoHeight) return { ...base, height: `${autoHeight}px` };
  return { ...base, ...placeholder };
}

export const IFRAME_STYLE: CSSProperties = {
  position: 'absolute',
  inset: 0,
  width: '100%',
  height: '100%',
  border: 0,
};

/** The height a resize message reports (rounded up), or null when it is not one meant for this frame. */
const reportedHeight = (payload: unknown, slug?: string): number | null => {
  if (!payload || typeof payload !== 'object') return null;
  const message = payload as {type?: unknown; slug?: unknown; height?: unknown};
  if (message.type !== RESIZE_MESSAGE_TYPE) return null;
  if (slug !== undefined && message.slug !== slug) return null;
  const height = Number(message.height);
  return Number.isFinite(height) && height > 0 ? Math.ceil(height) : null;
};

/**
 * The content height this iframe's page reports, trusting only messages from that iframe's window
 * and the expected ``origin`` (and, for widgets, the expected ``slug``). Null until it reports.
 */
export function useReportedHeight(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  enabled: boolean,
  origin: string | null,
  slug?: string,
): number | null {
  const [autoHeight, setAutoHeight] = useState<number | null>(null);
  useEffect(() => {
    if (!enabled || !origin) return;
    const handler = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return;
      if (event.origin !== origin) return;
      const height = reportedHeight(event.data, slug);
      if (height !== null) {
        setAutoHeight(height);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [iframeRef, enabled, origin, slug]);
  return autoHeight;
}
