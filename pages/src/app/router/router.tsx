import React, {Suspense, type ReactElement} from 'react';
import {createBrowserRouter, Navigate, type DataRouter, type RouteObject} from 'react-router';
import {LoadingIndicator} from '@/components/LoadingIndicator';
import {Layout} from '@/features/layout';
import {CMSPageComponent} from '@/features/cms';
import {HomepageResolver} from './HomepageResolver';
import {BlockPreviewPage} from '@/features/cms/components/BlockPreviewPage';
import {FooterPreviewPage} from '@/features/layout/components/FooterPreview/FooterPreviewPage';
import {LegacyLoginLinkRedirect} from './LegacyLoginLinkRedirect';
import {RouteDocumentTitle, type RouteHandle} from './RouteDocumentTitle';
import {EmbedBlockPage} from '@/features/cms/components/EmbedBlockPage';
import {EMBED_APP_ROUTES} from './embedAppRoutes';
import {NavigationPending, type LatestLocationSource} from './NavigationPending';
import {RouteErrorPage} from './RouteErrorPage';

// While a lazy route's chunk loads: the site's one loading look (the 24px spinner and its label), centred like the
// layout's own Suspense fallback (Container.tsx), so it matches the page's loading line that follows it. The boot
// spinner in pages/index.html (#root:empty::before) draws the same ring before the bundle runs.
const routeFallback = (
    <div className="page-loader" role="status">
        <LoadingIndicator label="Loading…"/>
    </div>
);

const lazyRoute = (element: ReactElement): ReactElement => (
    <Suspense fallback={routeFallback}>{element}</Suspense>
);

const titled = (title: string, meta: Omit<RouteHandle, 'title'> = {}): {handle: RouteHandle} => ({
    handle: {title, ...meta},
});

// Without its own error element a route error reaches React Router's developer screen (the raw message
// and stack trace, and no way back). Top-level routes replace the whole of #root on error.
const topLevelError = {errorElement: <RouteErrorPage inShell={false}/>};

const CURRENT_PROJECTS_DESCRIPTION =
    "This semester's Innovate to Grow student projects at UC Merced's School of Engineering: teams, partner organizations and abstracts.";
const PRESENTING_TEAMS_DESCRIPTION =
    "The student teams presenting at this semester's Innovate to Grow showcase at UC Merced, with their projects and partner organizations.";
const PAST_PROJECTS_DESCRIPTION =
    'Search the archive of past Innovate to Grow student projects at UC Merced, and collect them into lists to save, share or export.';
const ALL_PROJECTS_DESCRIPTION =
    "Search every Innovate to Grow student project at UC Merced, this semester's teams and the archive, and collect them into lists to save, share or export.";

// Auth pages (lazy)
const LoginPage = React.lazy(() => import('@/features/auth/components/pages/LoginPage').then(m => ({default: m.LoginPage})));
const RegisterPage = React.lazy(() => import('@/features/auth/components/pages/RegisterPage').then(m => ({default: m.RegisterPage})));
const AccountPage = React.lazy(() => import('@/features/auth/components/pages/AccountPage').then(m => ({default: m.AccountPage})));
const PastProjectCurationSharedLinksPage = React.lazy(() => import('@/features/auth/components/pages/PastProjectCurationSharedLinksPage').then(m => ({default: m.PastProjectCurationSharedLinksPage})));
const CompleteProfilePage = React.lazy(() => import('@/features/auth/components/pages/CompleteProfilePage').then(m => ({default: m.CompleteProfilePage})));
const ForgotPasswordPage = React.lazy(() => import('@/features/auth/components/pages/ForgotPasswordPage').then(m => ({default: m.ForgotPasswordPage})));
const VerifyEmailPage = React.lazy(() => import('@/features/auth/components/pages/VerifyEmailPage').then(m => ({default: m.VerifyEmailPage})));
const VerifyPhonePage = React.lazy(() => import('@/features/auth/components/pages/VerifyPhonePage').then(m => ({default: m.VerifyPhonePage})));

// Content pages (lazy) — only non-CMS pages
const NewsPage = React.lazy(() => import('@/routes/NewsPage').then(m => ({default: m.NewsPage})));
const NewsDetailPage = React.lazy(() => import('@/routes/NewsDetailPage').then(m => ({default: m.NewsDetailPage})));
const ProjectsPage = React.lazy(() => import('@/routes/ProjectsPage').then(m => ({default: m.ProjectsPage})));
const PastProjectsPage = React.lazy(() => import('@/routes/PastProjectsPage').then(m => ({default: m.PastProjectsPage})));
const AllProjectsPage = React.lazy(() => import('@/routes/AllProjectsPage').then(m => ({default: m.AllProjectsPage})));
const PresentingTeamsPage = React.lazy(() => import('@/routes/PresentingTeamsPage').then(m => ({default: m.PresentingTeamsPage})));
const ProjectDetailPage = React.lazy(() => import('@/routes/ProjectDetailPage').then(m => ({default: m.ProjectDetailPage})));
const SchedulePage = React.lazy(() => import('@/routes/SchedulePage').then(m => ({default: m.SchedulePage})));
const EventArchivePage = React.lazy(() => import('@/routes/EventArchivePage').then(m => ({default: m.EventArchivePage})));
const EventRegistrationPage = React.lazy(() => import('@/routes/EventRegistrationPage').then(m => ({default: m.EventRegistrationPage})));
const SubscribePage = React.lazy(() => import('@/routes/SubscribePage').then(m => ({default: m.SubscribePage})));
const LoginLinkPage = React.lazy(() => import('@/routes/LoginLinkPage').then(m => ({default: m.LoginLinkPage})));
const SmsLinkPage = React.lazy(() => import('@/routes/SmsLinkPage').then(m => ({default: m.SmsLinkPage})));
const EmailAuthLinkPage = React.lazy(() => import('@/routes/EmailAuthLinkPage').then(m => ({default: m.EmailAuthLinkPage})));
const ImpersonateLoginPage = React.lazy(() => import('@/routes/ImpersonateLoginPage').then(m => ({default: m.ImpersonateLoginPage})));

// Every page inside the site layout (menu, footer, content column).
const pageRoutes = (): RouteObject[] => [
    // support rout pointer for support old url
    {path: 'membership/events', element: lazyRoute(<EventRegistrationPage/>), ...titled('Event Registration')},

    // homepage — resolved dynamically from SiteSettings.homepage_route
    {index: true, element: <HomepageResolver/>},

    // news pages
    {path: 'news', element: lazyRoute(<NewsPage/>), ...titled('News')},
    {path: 'news/:id', element: lazyRoute(<NewsDetailPage/>)},

    // project pages (plain CMS routes like /projects, /sample-proposals
    {
        path: 'current-projects',
        element: lazyRoute(<ProjectsPage/>),
        ...titled('Current Projects', {description: CURRENT_PROJECTS_DESCRIPTION}),
    },
    {
        path: 'presenting-teams',
        element: lazyRoute(<PresentingTeamsPage/>),
        ...titled('Presenting Teams', {description: PRESENTING_TEAMS_DESCRIPTION}),
    },
    {
        path: 'past-projects',
        element: lazyRoute(<PastProjectsPage/>),
        ...titled('Past Projects', {description: PAST_PROJECTS_DESCRIPTION}),
    },
    {path: 'past-projects/project/:id', element: lazyRoute(<ProjectDetailPage/>)},
    // Shared curations are visitors' own lists (names and notes): kept out of search indexes.
    {
        path: 'past-projects/:shareId',
        element: lazyRoute(<PastProjectsPage/>),
        ...titled('Past Projects', {noindex: true}),
    },
    // Past Projects' builder over every project; its curations open at past-projects/:shareId too.
    {
        path: 'all-projects',
        element: lazyRoute(<AllProjectsPage/>),
        ...titled('All Projects', {description: ALL_PROJECTS_DESCRIPTION}),
    },
    {path: 'projects/:id', element: lazyRoute(<ProjectDetailPage/>)},
    // Legacy-site path still linked from CMS pages (/judges, /about-engsl).
    {path: 'projects-teams', element: <Navigate to="/current-projects" replace/>},

    // event pages (plain CMS routes like /event, /past-events are served
    // by the catch-all CMS route below)
    {path: 'event-registration', element: lazyRoute(<EventRegistrationPage/>), ...titled('Event Registration')},
    {path: 'events/:eventSlug', element: lazyRoute(<EventArchivePage/>)},
    {path: 'schedule', element: lazyRoute(<SchedulePage/>), ...titled('Event Schedule')},

    // Subscribe
    {path: 'subscribe', element: lazyRoute(<SubscribePage/>), ...titled('Subscriptions')},

    // Auto-login from email links
    {path: 'login-link', element: lazyRoute(<LoginLinkPage/>), ...titled('Sign In')},
    // SMS short links: the token is moved out of the address at start-up (/l/<token> → /l).
    {path: 'l', element: lazyRoute(<SmsLinkPage/>), ...titled('Opening Link')},
    {path: 'l/:token', element: lazyRoute(<SmsLinkPage/>), ...titled('Opening Link')},
    // Legacy aliases: previously-sent emails point at /magic-login (still
    // valid tokens) and /ticket-login (tokens already invalidated).
    {path: 'magic-login', element: <LegacyLoginLinkRedirect/>},
    {path: 'ticket-login', element: <LegacyLoginLinkRedirect/>},
    // Retired: old unsubscribe emails point at /unsubscribe-login, whose
    // tokens have all expired. Their email preferences live on /account;
    // the redirect drops the stale token instead of forwarding it.
    {path: 'unsubscribe-login', element: <Navigate to="/account" replace/>},
    {path: 'email-auth-link', element: lazyRoute(<EmailAuthLinkPage/>), ...titled('Sign In')},
    {path: 'impersonate-login', element: lazyRoute(<ImpersonateLoginPage/>), ...titled('Sign In')},

    // Convenience redirects
    {path: 'profile', element: <Navigate to="/account" replace/>},

    // Auth pages
    {path: 'login', element: lazyRoute(<LoginPage/>), ...titled('Sign In')},
    {path: 'register', element: lazyRoute(<RegisterPage/>)},
    {path: 'forgot-password', element: lazyRoute(<ForgotPasswordPage/>), ...titled('Forgot Password')},
    {path: 'verify-email', element: lazyRoute(<VerifyEmailPage/>), ...titled('Verify Your Email')},
    {path: 'verify-phone', element: lazyRoute(<VerifyPhonePage/>), ...titled('Verify Your Phone')},
    {path: 'complete-profile', element: lazyRoute(<CompleteProfilePage/>), ...titled('Complete Your Profile')},

    // Account management
    {path: 'account', element: lazyRoute(<AccountPage/>), ...titled('Account Dashboard')},
    {
        path: 'account/past-project-curation-shared-links',
        element: lazyRoute(<PastProjectCurationSharedLinksPage/>),
        ...titled('Past Project Curation Shared Links'),
    },

    // Catch-all CMS route
    {path: '*', element: <CMSPageComponent/>},
];

const buildRoutes = (latestLocation: LatestLocationSource): RouteObject[] => [
    // Block preview route — rendered in iframe for admin live preview, no menu/footer
    {path: '/_block-preview', element: <BlockPreviewPage/>, ...topLevelError},
    {path: '/_footer-preview', element: <FooterPreviewPage/>, ...topLevelError},
    // Public embed widget — rendered in third-party iframe, no menu/footer
    {path: '/_embed/:embedSlug', element: <EmbedBlockPage appRoutes={EMBED_APP_ROUTES}/>, ...topLevelError},
    {
        path: '/',
        element: (
            <>
                <RouteDocumentTitle/>
                <NavigationPending source={latestLocation}/>
                <Layout/>
            </>
        ),
        ...topLevelError,
        // A page's error renders in the page's place, inside the layout (menu, footer and title stay).
        children: [{errorElement: <RouteErrorPage/>, children: pageRoutes()}],
    },
];

export const createAppRouter = (): DataRouter => {
    // NavigationPending compares the router's latest location with the one React shows; the routes are
    // built before the router exists, so they reach it through this closure.
    const router: DataRouter = createBrowserRouter(buildRoutes({
        subscribe: (listener) => router.subscribe(listener),
        getLocationKey: () => router.state.location.key,
    }));
    return router;
};
