import {act} from '@testing-library/react';

export const navigateRef: {current: ((to: string) => void) | null} = {current: null};

/** Stands in for RouteDocumentTitle: names the tab from the route, before the tracker's effects run. */
export const ROUTE_TITLES: Record<string, string> = {
  '/presenting-teams': 'Presenting Teams | Innovate to Grow',
  '/current-projects': 'Current Projects | Innovate to Grow',
};

export const navigateTo = (to: string) => {
  act(() => {
    navigateRef.current?.(to);
  });
};

export const ORIGIN = window.location.origin;
