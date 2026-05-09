import { useMemo } from 'react';

interface EmbedData {
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

  if (!safeSrc) {
    return (
      <section className="cms-embed cms-embed--invalid" aria-label="Invalid embed">
        <p>Embed source is missing or not https.</p>
      </section>
    );
  }

  const aspect = parseAspectRatio(data.aspect_ratio);
  const fixedHeight =
    data.height !== undefined && data.height !== null && String(data.height).trim() !== ''
      ? Number(data.height)
      : null;
  const useFixedHeight = fixedHeight !== null && Number.isFinite(fixedHeight) && fixedHeight > 0;

  const frameStyle: React.CSSProperties = {
    position: 'relative',
    width: '100%',
    overflow: 'hidden',
    ...(useFixedHeight ? { height: `${fixedHeight}px` } : { aspectRatio: aspect ?? '16 / 9' }),
  };
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
