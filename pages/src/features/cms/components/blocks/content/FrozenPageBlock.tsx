import { API_BASE_URL } from '@/lib/api-client';

interface FrozenPageData {
  frozen_page_id?: string;
  heading?: string;
  height?: number | string;
}

const DEFAULT_HEIGHT = 600;

export const FrozenPageBlock = ({
  data,
  previewMode = false,
}: {
  data: FrozenPageData;
  previewMode?: boolean;
}) => {
  const id = (data.frozen_page_id || '').trim();

  if (!id) {
    return (
      <section className="cms-frozen-page cms-frozen-page--invalid" aria-label="Invalid frozen page">
        <p>Frozen page is not selected.</p>
      </section>
    );
  }

  const parsed =
    data.height !== undefined && data.height !== null && String(data.height).trim() !== ''
      ? Number(data.height)
      : NaN;
  const height = Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_HEIGHT;

  // The frozen document is served by Django and rendered in a fully sandboxed
  // iframe. sandbox="" disables scripts/forms/same-origin, so the document can't
  // postMessage its height back — auto-resize is impossible and the height is
  // admin-configurable (default 600px).
  const apiBase = (API_BASE_URL || '/api').replace(/\/$/, '');
  const src = `${apiBase}/cms/frozen/${encodeURIComponent(id)}/`;

  return (
    <section className="cms-frozen-page">
      {data.heading && <h2 className="section-title">{data.heading}</h2>}
      <iframe
        src={src}
        title={data.heading || 'Imported page'}
        sandbox=""
        loading={previewMode ? 'eager' : 'lazy'}
        referrerPolicy="no-referrer"
        style={{ width: '100%', height: `${height}px`, border: 0 }}
      />
    </section>
  );
};
