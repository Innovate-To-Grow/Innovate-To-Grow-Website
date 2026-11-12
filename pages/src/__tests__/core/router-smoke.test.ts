import {Suspense, isValidElement, type ReactElement, type SuspenseProps} from 'react';
import {matchRoutes, type RouteObject} from 'react-router';
import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, it, expect} from 'vitest';

/** The route with `path` anywhere under `routes` (pages sit inside a pathless error-boundary route). */
const findRoute = (routes: RouteObject[], path: string): RouteObject | undefined => {
    for (const route of routes) {
        if (route.path === path) return route;
        const nested = route.children ? findRoute(route.children, path) : undefined;
        if (nested) return nested;
    }
    return undefined;
};

describe('Router', () => {
    it('router object is created without errors', async () => {
        const {createAppRouter} = await import('@/app/router');
        const router = createAppRouter();
        expect(router).toBeDefined();
        expect(router.routes).toBeDefined();
        expect(router.routes.length).toBeGreaterThan(0);
    });

    it.each([
        ['/past-projects/project/project-123', 'past-projects/project/:id'],
        ['/past-projects/share-123', 'past-projects/:shareId'],
        ['/all-projects', 'all-projects'],
        ['/account/past-project-curation-shared-links', 'account/past-project-curation-shared-links'],
        ['/news/article-123', 'news/:id'],
        // A CMS page, copy and sponsors edited in the CMS.
        ['/acknowledgement', '*'],
        ['/an-unregistered-cms-path', '*'],
    ])('matches %s to the most specific route before the CMS catch-all', async (pathname, expectedPath) => {
        const {createAppRouter} = await import('@/app/router');
        const router = createAppRouter();

        const matches = matchRoutes(router.routes, pathname);

        expect(matches?.at(-1)?.route.path).toBe(expectedPath);
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
        'presenting-teams',
        'past-projects',
        'all-projects',
        'projects/:id',
        'schedule',
        'events/:eventSlug',
        'event-registration',
        'membership/events',
        'subscribe',
        'login-link',
        'l',
        'l/:token',
        'email-auth-link',
        'impersonate-login',
    ];

    it.each(lazyRoutePaths)('lazy route %s is wrapped in Suspense', async (path) => {
        const {createAppRouter} = await import('@/app/router');
        const router = createAppRouter();
        const route = findRoute(router.routes, path);

        expect(route, `route ${path} not found`).toBeDefined();
        expect(isValidElement(route?.element)).toBe(true);
        // React stores the component reference on `.type`. If the route element is
        // a bare lazy component instead of <Suspense>, a slow chunk load leaves
        // the UI frozen on the previous page.
        expect((route?.element as { type: unknown }).type).toBe(Suspense);
    });

    describe('while a lazy route loads', () => {
        afterEach(cleanup);

        it.each(lazyRoutePaths)('route %s shows the shared loading indicator, centred', async (path) => {
            const {createAppRouter} = await import('@/app/router');
            const route = findRoute(createAppRouter().routes, path);
            const {fallback} = (route?.element as ReactElement<SuspenseProps>).props;

            render(fallback as ReactElement);

            // The look of the page's own loading line that follows it (LoadingIndicator), not a bigger bare ring.
            const status = screen.getByRole('status');
            expect(status).toHaveClass('page-loader');
            expect(status).toHaveTextContent(/^Loading…$/);
            expect(status.querySelector('.loading-indicator .loading-indicator-spinner')).toHaveAttribute('aria-hidden', 'true');
            expect(status).not.toHaveAttribute('style');
        });
    });

    it('titles All Projects and describes it for search engines', async () => {
        const {createAppRouter} = await import('@/app/router');
        const route = findRoute(createAppRouter().routes, 'all-projects');

        expect(route?.handle).toEqual({
            title: 'All Projects',
            description: expect.stringMatching(/^Search every Innovate to Grow student project at UC Merced/),
        });
        expect(route?.handle).not.toHaveProperty('noindex');
    });

    it.each(['/', '/_block-preview', '/_footer-preview', '/_embed/:embedSlug'])(
        'top-level route %s has an error element, so a route error never shows the developer screen',
        async (path) => {
            const {createAppRouter} = await import('@/app/router');
            const route = createAppRouter().routes.find((candidate) => candidate.path === path);

            expect(isValidElement(route?.errorElement)).toBe(true);
        },
    );

    it('catches page errors inside the layout, in a pathless route around every page', async () => {
        const {createAppRouter} = await import('@/app/router');
        const rootRoute = createAppRouter().routes.find((route) => route.path === '/');
        const [pages] = rootRoute?.children ?? [];

        expect(pages?.path).toBeUndefined();
        expect(isValidElement(pages?.errorElement)).toBe(true);
        expect(findRoute(pages?.children ?? [], 'current-projects')).toBeDefined();
    });
});
