import { useEffect, useMemo, useRef, useState } from 'react';

interface EmbedWidgetData {
  slug: string;
  heading?: string;
  height?: number | string;
  aspect_ratio?: string;
  hidden_sections?: string[];
  hide_section_titles?: boolean;
}

const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

function parseAspectRatio(value?: string): string | null {
  if (!value) return null;
  const match = /^(\d+):(\d+)$/.exec(value);
  if (!match) return null;
  const w = Number(match[1]);
  const h = Number(match[2]);
  if (!w || !h) return null;
  return `${w} / ${h}`;
}

export const EmbedWidgetBlock: React.FC<{
  data: EmbedWidgetData;
  previewMode?: boolean;
}> = ({ data, previewMode = false }) => {
  const slug = useMemo(() => (data.slug || '').trim().toLowerCase(), [data.slug]);
  const validSlug = SLUG_RE.test(slug);

  const aspect = parseAspectRatio(data.aspect_ratio);
  const fixedHeight =
    data.height !== undefined && data.height !== null && String(data.height).trim() !== ''
      ? Number(data.height)
      : null;
  const useFixedHeight = fixedHeight !== null && Number.isFinite(fixedHeight) && fixedHeight > 0;
  const useAutoResize = !useFixedHeight && !aspect;

  const [autoHeight, setAutoHeight] = useState<number | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    if (!useAutoResize || !validSlug) return;
    const handler = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return;
      if (event.origin !== window.location.origin) return;
      const payload = event.data;
      if (!payload || typeof payload !== 'object') return;
      if (payload.type !== 'i2g-embed-resize') return;
      if (payload.slug !== slug) return;
      const height = Number(payload.height);
      if (Number.isFinite(height) && height > 0) {
        setAutoHeight(Math.ceil(height));
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [slug, validSlug, useAutoResize]);

  if (!validSlug) {
    return (
      <section className="cms-embed-widget cms-embed-widget--invalid" aria-label="Invalid embed widget">
        <p>Embed widget slug is missing or invalid.</p>
      </section>
    );
  }

  const queryParams = new URLSearchParams();
  const hiddenSections = Array.isArray(data.hidden_sections) ? data.hidden_sections : null;
  if (!hiddenSections && data.hide_section_titles) queryParams.set('hide-titles', '1');
  if (hiddenSections?.length) {
    queryParams.set('hide-sections', hiddenSections.join(','));
  }
  const query = queryParams.toString() ? `?${queryParams.toString()}` : '';
  const src = `/_embed/${encodeURIComponent(slug)}${query}`;

  let frameStyle: React.CSSProperties = {
    position: 'relative',
    width: '100%',
    overflow: 'hidden',
  };
  if (useFixedHeight) {
    frameStyle = { ...frameStyle, height: `${fixedHeight}px` };
  } else if (aspect) {
    frameStyle = { ...frameStyle, aspectRatio: aspect };
  } else {
    frameStyle = {
      ...frameStyle,
      height: autoHeight ? `${autoHeight}px` : previewMode ? '360px' : '120px',
    };
  }

  const iframeStyle: React.CSSProperties = {
    position: 'absolute',
    inset: 0,
    width: '100%',
    height: '100%',
    border: 0,
  };

  return (
    <section className="cms-embed-widget">
      {data.heading && <h2 className="section-title">{data.heading}</h2>}
      <div className="cms-embed-widget__frame" style={frameStyle}>
        <iframe
          ref={iframeRef}
          src={src}
          title={data.heading || `Embedded widget: ${slug}`}
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
          loading={previewMode ? 'eager' : 'lazy'}
          referrerPolicy="no-referrer-when-downgrade"
          style={iframeStyle}
        />
      </div>
    </section>
  );
};
