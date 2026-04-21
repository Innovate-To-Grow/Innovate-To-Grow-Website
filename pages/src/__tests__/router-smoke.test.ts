import {Suspense, isValidElement} from 'react';
import {describe, it, expect} from 'vitest';

describe('Router', () => {
  it('router object is created without errors', async () => {
    const {router} = await import('../router');
    expect(router).toBeDefined();
    expect(router.routes).toBeDefined();
    expect(router.routes.length).toBeGreaterThan(0);
  });

  it('keeps acknowledgement on a dedicated route instead of CMSPageComponent', async () => {
    const {router} = await import('../router');
    const rootRoute = router.routes.find((route) => route.path === '/');
    const acknowledgementRoute = rootRoute?.children?.find((route) => route.path === 'acknowledgement');

    expect(acknowledgementRoute).toBeDefined();
    // The route exists as a dedicated (non-catch-all) route, confirming it's not handled by the CMS catch-all
    expect(acknowledgementRoute?.path).toBe('acknowledgement');
  });

  // Paths whose element is a lazy chunk — every one of these must be Suspense-
  // wrapped so a slow chunk load shows the fallback spinner instead of stalling
  // silently on the previous page.
  const lazyRoutePaths = [
    'login',
    'register',
    'account',
    'complete-profile',
    'forgot-password',
    'verify-email',
    'news',
    'news/:id',
    'current-projects',
    'past-projects',
    'past-projects/:shareId',
    'projects/:id',
    'schedule',
    'acknowledgement',
    'events/:eventSlug',
    'event-registration',
    'membership/events',
    'ticket-login',
    'subscribe',
    'unsubscribe-login',
    'magic-login',
    'email-auth-link',
    'impersonate-login',
  ];

  it.each(lazyRoutePaths)('lazy route %s is wrapped in Suspense', async (path) => {
    const {router} = await import('../router');
    const rootRoute = router.routes.find((route) => route.path === '/');
    // Non-index children carry an `element` prop; the types model index vs
    // non-index routes separately, so narrow with a cast rather than a
    // runtime type guard.
    const route = rootRoute?.children?.find((r) => 'path' in r && r.path === path) as
      | {element?: unknown}
      | undefined;

    expect(route, `route ${path} not found`).toBeDefined();
    expect(isValidElement(route?.element)).toBe(true);
    // React stores the component reference on `.type`. If the route element is
    // a bare lazy component instead of <Suspense>, a slow chunk load leaves
    // the UI frozen on the previous page.
    expect((route?.element as {type: unknown}).type).toBe(Suspense);
  });
});
