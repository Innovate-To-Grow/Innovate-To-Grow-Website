import React, {type LazyExoticComponent, type ComponentType} from 'react';
import type {EmbedAppRouteProps, EmbedAppRoutes} from '@/features/cms/components/embed/EmbedBlockPage';

/**
 * Registry of app routes that can be rendered inside a CMS Embed Widget iframe.
 *
 * Keys must match the entries in `src/apps/cms/app_routes.py` on the backend. It lives in the app layer
 * because it composes route pages; the router hands it to the CMS `EmbedBlockPage`.
 * Each component is rendered standalone inside `/_embed/:embedSlug` — it must
 * therefore not depend on the main site Layout (menu / footer / etc.).
 */
export const EMBED_APP_ROUTE_COMPONENTS: Record<string, LazyExoticComponent<ComponentType<EmbedAppRouteProps>>> = {
  '/schedule': React.lazy(() => import('@/routes/events/SchedulePage/page').then((m) => ({default: m.SchedulePage}))),
  '/current-projects': React.lazy(() => import('@/routes/projects/ProjectsPage').then((m) => ({default: m.ProjectsPage}))),
  '/presenting-teams': React.lazy(() => import('@/routes/projects/PresentingTeamsPage').then((m) => ({default: m.PresentingTeamsPage}))),
  '/past-projects': React.lazy(() => import('@/routes/projects/PastProjectsPage').then((m) => ({default: m.PastProjectsPage}))),
  '/all-projects': React.lazy(() => import('@/routes/projects/AllProjectsPage').then((m) => ({default: m.AllProjectsPage}))),
  '/acknowledgement': React.lazy(() => import('@/routes/events/AcknowledgementPage').then((m) => ({default: m.AcknowledgementPage}))),
  '/news': React.lazy(() => import('@/routes/news/NewsPage').then((m) => ({default: m.NewsPage}))),
  '/event-registration': React.lazy(() => import('@/routes/events/EventRegistrationPage/page').then((m) => ({default: m.EventRegistrationPage}))),
  '/subscribe': React.lazy(() => import('@/routes/subscription/SubscribePage/page').then((m) => ({default: m.SubscribePage}))),
};

/**
 * Embed routes whose component accepts a pinned `CurrentProjectSchedule`
 * (`scheduleId` prop). Must match the routes flagged `schedule_selectable`
 * in `src/apps/cms/app_routes.py`.
 */
export const SCHEDULE_SELECTABLE_EMBED_ROUTES: ReadonlySet<string> = new Set(['/schedule']);

export function resolveEmbedAppRoute(route: string | undefined | null): LazyExoticComponent<ComponentType<EmbedAppRouteProps>> | null {
  if (!route) return null;
  return EMBED_APP_ROUTE_COMPONENTS[route] ?? null;
}

export function embedRouteSupportsSchedule(route: string | undefined | null): boolean {
  return Boolean(route && SCHEDULE_SELECTABLE_EMBED_ROUTES.has(route));
}

export const EMBED_APP_ROUTES: EmbedAppRoutes = {
  resolve: resolveEmbedAppRoute,
  supportsSchedule: embedRouteSupportsSchedule,
};
