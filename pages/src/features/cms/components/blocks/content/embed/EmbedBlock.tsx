import { useMemo, useRef } from 'react';
import { frameStyleFor, IFRAME_STYLE, parseAspectRatio, parseFixedHeight, useReportedHeight } from './embedFrame';

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

// Default placeholder until (or unless) a cooperating embed reports its content height.
const PLACEHOLDER_STYLE = { aspectRatio: '16 / 9' };

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

export const EmbedBlock = ({
  data,
  previewMode = false,
}: { data: EmbedData; previewMode?: boolean }) => {
  const safeSrc = useMemo(() => normalizeHttpsUrl(data.src), [data.src]);

  const aspect = parseAspectRatio(data.aspect_ratio);
  const fixedHeight = parseFixedHeight(data.height);
  // Auto-fit height only in the pure default case: no explicit fixed height and
  // no explicit aspect ratio. Setting either is the editor's opt-out, and a
  // non-cooperating third-party site simply never reports, so it stays at the
  // 16/9 placeholder below — no regression for ordinary embeds.
  const useAutoResize = fixedHeight === null && !aspect;

  // The origin we accept resize messages from — the embed's own origin.
  const embedOrigin = useMemo(() => {
    if (!safeSrc) return null;
    try {
      return new URL(safeSrc).origin;
    } catch {
      return null;
    }
  }, [safeSrc]);

  const iframeRef = useRef<HTMLIFrameElement>(null);
  // Only trust messages from this iframe's window AND its exact origin.
  const autoHeight = useReportedHeight(iframeRef, useAutoResize, embedOrigin);

  if (!safeSrc) {
    return (
      <section className="cms-embed cms-embed--invalid itg-notice" aria-label="Invalid embed">
        <p>Embed source is missing or not https.</p>
      </section>
    );
  }

  return (
    <section className="cms-embed">
      {data.heading && <h2 className="section-title itg-section-title">{data.heading}</h2>}
      <div className="cms-embed__frame" style={frameStyleFor(fixedHeight, aspect, autoHeight, PLACEHOLDER_STYLE)}>
        <iframe
          ref={iframeRef}
          src={safeSrc}
          title={data.title || data.heading || 'Embedded content'}
          sandbox={data.sandbox || DEFAULT_SANDBOX}
          allow={data.allow || undefined}
          allowFullScreen={Boolean(data.allowfullscreen)}
          loading={previewMode ? 'eager' : 'lazy'}
          referrerPolicy="no-referrer-when-downgrade"
          style={IFRAME_STYLE}
        />
      </div>
    </section>
  );
};
