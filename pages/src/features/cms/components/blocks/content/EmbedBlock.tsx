import { useEffect, useMemo, useRef, useState } from 'react';

export interface EmbedData {
  src: string;
  title?: string;
  heading?: string;
  height?: number | string;
  aspect_ratio?: string;
  sandbox?: string;
  allow?: string;
  allowfullscreen?: boolean;
}

const DEFAULT_SANDBOX = 'allow-scripts allow-same-origin allow-forms allow-popups';

// A cooperating embedded page (e.g. our own archive site) posts its content
// height so we can grow the iframe to fit. Same contract the CMS uses for
// same-origin embed widgets.
const RESIZE_MESSAGE_TYPE = 'i2g-embed-resize';

function normalizeHttpsUrl(src: string): string | null {
  if (!src || typeof src !== 'string') return null;
  try {
    const url = new URL(src.trim());
    if (url.protocol !== 'https:') return null;
    if (!url.hostname) return null;
    return url.toString();
  } catch {
    return null;
  }
}

function parseAspectRatio(value?: string): string | null {
  if (!value) return null;
  const match = /^(\d+):(\d+)$/.exec(value);
  if (!match) return null;
  const w = Number(match[1]);
  const h = Number(match[2]);
  if (!w || !h) return null;
  return `${w} / ${h}`;
}

export const EmbedBlock = ({
  data,
  previewMode = false,
}: { data: EmbedData; previewMode?: boolean }) => {
  const safeSrc = useMemo(() => normalizeHttpsUrl(data.src), [data.src]);

  const aspect = parseAspectRatio(data.aspect_ratio);
  const fixedHeight =
    data.height !== undefined && data.height !== null && String(data.height).trim() !== ''
      ? Number(data.height)
      : null;
  const useFixedHeight = fixedHeight !== null && Number.isFinite(fixedHeight) && fixedHeight > 0;
  // Auto-fit height only in the pure default case: no explicit fixed height and
  // no explicit aspect ratio. Setting either is the editor's opt-out, and a
  // non-cooperating third-party site simply never reports, so it stays at the
  // 16/9 placeholder below — no regression for ordinary embeds.
  const useAutoResize = !useFixedHeight && !aspect;

  // The origin we accept resize messages from — the embed's own origin.
  const embedOrigin = useMemo(() => {
    if (!safeSrc) return null;
    try {
      return new URL(safeSrc).origin;
    } catch {
      return null;
    }
  }, [safeSrc]);

  const [autoHeight, setAutoHeight] = useState<number | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    if (!useAutoResize || !embedOrigin) return;
    const handler = (event: MessageEvent) => {
      // Only trust messages from this iframe's window AND its exact origin.
      if (event.source !== iframeRef.current?.contentWindow) return;
      if (event.origin !== embedOrigin) return;
      const payload = event.data;
      if (!payload || typeof payload !== 'object') return;
      if (payload.type !== RESIZE_MESSAGE_TYPE) return;
      const height = Number(payload.height);
      if (Number.isFinite(height) && height > 0) {
        setAutoHeight(Math.ceil(height));
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [useAutoResize, embedOrigin]);

  if (!safeSrc) {
    return (
      <section className="cms-embed cms-embed--invalid" aria-label="Invalid embed">
        <p>Embed source is missing or not https.</p>
      </section>
    );
  }

  let frameStyle: React.CSSProperties = {
    position: 'relative',
    width: '100%',
    overflow: 'hidden',
  };
  if (useFixedHeight) {
    frameStyle = { ...frameStyle, height: `${fixedHeight}px` };
  } else if (aspect) {
    frameStyle = { ...frameStyle, aspectRatio: aspect };
  } else if (autoHeight) {
    // A cooperating embed reported its content height — fit to it exactly.
    frameStyle = { ...frameStyle, height: `${autoHeight}px` };
  } else {
    // Default placeholder until (or unless) a height is reported.
    frameStyle = { ...frameStyle, aspectRatio: '16 / 9' };
  }

  const iframeStyle: React.CSSProperties = {
    position: 'absolute',
    inset: 0,
    width: '100%',
    height: '100%',
    border: 0,
  };

  return (
    <section className="cms-embed">
      {data.heading && <h2 className="section-title">{data.heading}</h2>}
      <div className="cms-embed__frame" style={frameStyle}>
        <iframe
          ref={iframeRef}
          src={safeSrc}
          title={data.title || data.heading || 'Embedded content'}
          sandbox={data.sandbox || DEFAULT_SANDBOX}
          allow={data.allow || undefined}
          allowFullScreen={Boolean(data.allowfullscreen)}
          loading={previewMode ? 'eager' : 'lazy'}
          referrerPolicy="no-referrer-when-downgrade"
          style={iframeStyle}
        />
      </div>
    </section>
  );
};
