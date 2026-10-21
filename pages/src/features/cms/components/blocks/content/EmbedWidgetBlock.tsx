import { useMemo, useRef } from 'react';
import { normalizeScheduleId } from '@/features/cms/components/embedScheduleId';
import { frameStyleFor, IFRAME_STYLE, parseFixedHeight, parseAspectRatio, useReportedHeight } from './embedFrame';

export interface EmbedWidgetData {
  slug: string;
  heading?: string;
  height?: number | string;
  aspect_ratio?: string;
  hidden_sections?: string[];
  hide_section_titles?: boolean;
  /** Block-level CurrentProjectSchedule override for /schedule widgets (e.g. a specific year). */
  schedule_id?: string | null;
}

const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

function widgetSrc(slug: string, data: EmbedWidgetData): string {
  const queryParams = new URLSearchParams();
  const hiddenSections = Array.isArray(data.hidden_sections) ? data.hidden_sections : null;
  if (!hiddenSections && data.hide_section_titles) queryParams.set('hide-titles', '1');
  if (hiddenSections?.length) {
    queryParams.set('hide-sections', hiddenSections.join(','));
  }
  // The block's pinned schedule beats the widget's default; EmbedBlockPage
  // reads it back off the iframe URL.
  const scheduleId = normalizeScheduleId(data.schedule_id);
  if (scheduleId) queryParams.set('schedule_id', scheduleId);
  const query = queryParams.toString() ? `?${queryParams.toString()}` : '';
  return `/_embed/${encodeURIComponent(slug)}${query}`;
}

export const EmbedWidgetBlock = ({ data, previewMode = false }: {
  data: EmbedWidgetData;
  previewMode?: boolean;
}) => {
  const slug = useMemo(() => (data.slug || '').trim().toLowerCase(), [data.slug]);
  const validSlug = SLUG_RE.test(slug);

  const aspect = parseAspectRatio(data.aspect_ratio);
  const fixedHeight = parseFixedHeight(data.height);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const autoHeight = useReportedHeight(iframeRef, validSlug && fixedHeight === null && !aspect, window.location.origin, slug);

  if (!validSlug) {
    return (
      <section className="cms-embed-widget cms-embed-widget--invalid itg-notice" aria-label="Invalid embed widget">
        <p>Embed widget slug is missing or invalid.</p>
      </section>
    );
  }

  return (
    <section className="cms-embed-widget">
      {data.heading && <h2 className="section-title itg-section-title">{data.heading}</h2>}
      <div className="cms-embed-widget__frame" style={frameStyleFor(fixedHeight, aspect, autoHeight, {height: previewMode ? '360px' : '120px'})}>
        <iframe
          ref={iframeRef}
          src={widgetSrc(slug, data)}
          title={data.heading || `Embedded widget: ${slug}`}
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
          loading={previewMode ? 'eager' : 'lazy'}
          referrerPolicy="no-referrer-when-downgrade"
          style={IFRAME_STYLE}
        />
      </div>
    </section>
  );
};
