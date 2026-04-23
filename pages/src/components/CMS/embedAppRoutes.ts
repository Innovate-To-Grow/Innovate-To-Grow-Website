import React, {type LazyExoticComponent, type ComponentType} from 'react';

/**
 * Registry of app routes that can be rendered inside a CMS Embed Widget iframe.
 *
 * Keys must match the entries in `src/cms/app_routes.py` on the backend.
 * Each component is rendered standalone inside `/_embed/:embedSlug` — it must
 * therefore not depend on the main site Layout (menu / footer / etc.).
 */
export const EMBED_APP_ROUTE_COMPONENTS: Record<string, LazyExoticComponent<ComponentType>> = {
  '/schedule': React.lazy(() => import('../../pages/SchedulePage').then((m) => ({default: m.SchedulePage}))),
  '/current-projects': React.lazy(() => import('../../pages/ProjectsPage').then((m) => ({default: m.ProjectsPage}))),
  '/presenting-teams': React.lazy(() => import('../../pages/PresentingTeamsPage').then((m) => ({default: m.PresentingTeamsPage}))),
  '/past-projects': React.lazy(() => import('../../pages/PastProjectsPage').then((m) => ({default: m.PastProjectsPage}))),
  '/acknowledgement': React.lazy(() => import('../../pages/AcknowledgementPage').then((m) => ({default: m.AcknowledgementPage}))),
  '/news': React.lazy(() => import('../../pages/NewsPage').then((m) => ({default: m.NewsPage}))),
  '/event-registration': React.lazy(() => import('../../pages/EventRegistrationPage').then((m) => ({default: m.EventRegistrationPage}))),
  '/subscribe': React.lazy(() => import('../../pages/SubscribePage').then((m) => ({default: m.SubscribePage}))),
};

export function resolveEmbedAppRoute(route: string | undefined | null): LazyExoticComponent<ComponentType> | null {
  if (!route) return null;
  return EMBED_APP_ROUTE_COMPONENTS[route] ?? null;
}
