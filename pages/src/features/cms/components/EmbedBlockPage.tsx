import { createElement, Suspense, useMemo, useRef, type ComponentType } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { BlockRenderer } from './BlockRenderer';
import { cmsPageClassName } from './pageClassName';
import type { CMSEmbedResponse } from '@/features/cms/api';
import { EMBED_BODY_CSS, useBaseTargetBlank, useEmbedData, useHeadStyle, useReportHeightToParent } from './embed/useEmbedDocument';
import { normalizeScheduleId } from './embedScheduleId';
import {
  SECTION_TITLES_KEY,
  buildHiddenSectionsCss,
  isTruthyParam,
  normalizeHiddenSections,
  parseHiddenSectionsParam,
} from './hiddenSections';

/**
 * Public embed page rendered inside a third-party iframe.
 *
 * - Fetches a single embeddable block by slug from /cms/embed/<slug>/.
 * - Renders it inside the correct `page_css_class` wrapper so block styles
 *   (which cascade from `.cms-page ...` selectors) apply.
 * - Injects page_css scoped to the page.
 * - Reports its own height to the parent window via postMessage so the iframe
 *   can auto-resize (message type `i2g-embed-resize`).
 * - Adds <base target="_blank"> so any internal links open in a new window,
 *   preventing users from getting stuck in the chromeless iframe view.
 */

export interface EmbedAppRouteProps {
  scheduleId?: string | null;
}

/** The app routes a CMS embed widget may render; supplied by the app layer, which owns the route pages. */
export interface EmbedAppRoutes {
  resolve: (route: string | undefined | null) => ComponentType<EmbedAppRouteProps> | null;
  /** Routes whose component accepts a pinned `CurrentProjectSchedule` (`scheduleId` prop). */
  supportsSchedule: (route: string | undefined | null) => boolean;
}

export const EmbedBlockPage = ({appRoutes}: {appRoutes: EmbedAppRoutes}) => {
  const { embedSlug } = useParams<{ embedSlug: string }>();
  const [searchParams] = useSearchParams();
  const { data, notFound } = useEmbedData(embedSlug);

  const hideTitlesFromQuery = isTruthyParam(searchParams.get('hide-titles'));
  const hideSectionsParam = searchParams.get('hide-sections');
  // Block-level schedule override (see EmbedWidgetBlock); wins over the widget's own default.
  const scheduleIdFromQuery = normalizeScheduleId(searchParams.get('schedule_id'));
  const hiddenSections = useMemo(
    () =>
      normalizeHiddenSections([
        ...(data?.hidden_sections ?? []),
        ...parseHiddenSectionsParam(hideSectionsParam),
        ...(hideTitlesFromQuery || data?.hide_section_titles ? [SECTION_TITLES_KEY] : []),
      ]),
    [data?.hidden_sections, data?.hide_section_titles, hideSectionsParam, hideTitlesFromQuery],
  );
  const hiddenSectionsCss = useMemo(
    () => buildHiddenSectionsCss(hiddenSections),
    [hiddenSections],
  );

  useBaseTargetBlank();
  useHeadStyle('itg-embed-body', EMBED_BODY_CSS);
  // page_css comes from the parent CMS page.
  useHeadStyle('itg-embed-page-css', data?.page_css);
  // Hide safe preset sections when requested by widget config or preview query params.
  useHeadStyle('itg-embed-hide-sections', hiddenSectionsCss);
  // Report height to parent (once data is rendered, and on any size change).
  useReportHeightToParent(embedSlug, Boolean(data));

  const containerRef = useRef<HTMLDivElement>(null);

  if (notFound || !embedSlug) {
    return (
      <p className="cms-embed-message">
        Embed not found.
      </p>
    );
  }
  if (!data) return null;

  return (
    <EmbedBody data={data} containerRef={containerRef} scheduleIdOverride={scheduleIdFromQuery} appRoutes={appRoutes} />
  );
};

interface EmbedBodyProps {
  data: CMSEmbedResponse;
  containerRef: React.RefObject<HTMLDivElement | null>;
  scheduleIdOverride?: string | null;
  appRoutes: EmbedAppRoutes;
}

const EmbedBody = ({ data, containerRef, scheduleIdOverride = null, appRoutes }: EmbedBodyProps) => {
  const appRouteComponent = useMemo(
    () => (data.widget_type === 'app_route' ? appRoutes.resolve(data.app_route) : null),
    [appRoutes, data.widget_type, data.app_route],
  );

  if (data.widget_type === 'app_route') {
    if (!appRouteComponent) {
      return (
        <p className="cms-embed-message">
          App route <code>{data.app_route}</code> is not available for embedding.
        </p>
      );
    }
    // Precedence: block override (iframe query) > widget default (embed payload) > active schedule.
    const appRouteProps = appRoutes.supportsSchedule(data.app_route)
      ? {scheduleId: scheduleIdOverride || data.schedule_id || null}
      : undefined;
    return (
      <div ref={containerRef} className="cms-embed-app-route">
        <Suspense fallback={null}>{createElement(appRouteComponent, appRouteProps)}</Suspense>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={cmsPageClassName(data.page_css_class)}>
      <BlockRenderer blocks={data.blocks} />
    </div>
  );
};
