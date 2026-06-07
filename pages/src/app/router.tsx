import React, {Suspense, type ReactElement} from 'react';
import {createBrowserRouter, Navigate} from 'react-router-dom';
import {Layout} from '@/features/layout';
import {CMSPageComponent} from '@/features/cms';
import {HomepageResolver} from './HomepageResolver';
import {BlockPreviewPage} from '@/features/cms/components/BlockPreviewPage';
import {LegacyLoginLinkRedirect} from './LegacyLoginLinkRedirect';
import {EmbedBlockPage} from '@/features/cms/components/EmbedBlockPage';

// Matches the inline spinner in pages/index.html (#root:empty::before) so
// lazy-route fallbacks and the initial-load spinner share one visual language.
const routeFallback = (
    <div
        aria-label="Loading"
        role="status"
        style={{
            display: 'block',
            width: 44,
            height: 44,
            margin: '96px auto',
            border: '3px solid rgba(15, 45, 82, 0.15)',
            borderTopColor: 'var(--itg-color-primary, #0f2d52)',
            borderRadius: '50%',
            animation: 'itg-init-loader-spin 0.9s linear infinite',
        }}
    />
);

const lazyRoute = (element: ReactElement): ReactElement => (
    <Suspense fallback={routeFallback}>{element}</Suspense>
);

// Auth pages (lazy)
const LoginPage = React.lazy(() => import('@/features/auth/components/pages/LoginPage').then(m => ({default: m.LoginPage})));
const RegisterPage = React.lazy(() => import('@/features/auth/components/pages/RegisterPage').then(m => ({default: m.RegisterPage})));
const AccountPage = React.lazy(() => import('@/features/auth/components/pages/AccountPage').then(m => ({default: m.AccountPage})));
const CompleteProfilePage = React.lazy(() => import('@/features/auth/components/pages/CompleteProfilePage').then(m => ({default: m.CompleteProfilePage})));
const ForgotPasswordPage = React.lazy(() => import('@/features/auth/components/pages/ForgotPasswordPage').then(m => ({default: m.ForgotPasswordPage})));
const VerifyEmailPage = React.lazy(() => import('@/features/auth/components/pages/VerifyEmailPage').then(m => ({default: m.VerifyEmailPage})));

// Content pages (lazy) — only non-CMS pages
const NewsPage = React.lazy(() => import('@/routes/NewsPage').then(m => ({default: m.NewsPage})));
const NewsDetailPage = React.lazy(() => import('@/routes/NewsDetailPage').then(m => ({default: m.NewsDetailPage})));
const ProjectsPage = React.lazy(() => import('@/routes/ProjectsPage').then(m => ({default: m.ProjectsPage})));
const PastProjectsPage = React.lazy(() => import('@/routes/PastProjectsPage').then(m => ({default: m.PastProjectsPage})));
const PresentingTeamsPage = React.lazy(() => import('@/routes/PresentingTeamsPage').then(m => ({default: m.PresentingTeamsPage})));
const ProjectDetailPage = React.lazy(() => import('@/routes/ProjectDetailPage').then(m => ({default: m.ProjectDetailPage})));
const SchedulePage = React.lazy(() => import('@/routes/SchedulePage').then(m => ({default: m.SchedulePage})));
const AcknowledgementPage = React.lazy(() => import('@/routes/AcknowledgementPage').then(m => ({default: m.AcknowledgementPage})));
const EventArchivePage = React.lazy(() => import('@/routes/EventArchivePage').then(m => ({default: m.EventArchivePage})));
const EventRegistrationPage = React.lazy(() => import('@/routes/EventRegistrationPage').then(m => ({default: m.EventRegistrationPage})));
const SubscribePage = React.lazy(() => import('@/routes/SubscribePage').then(m => ({default: m.SubscribePage})));
const UnsubscribeLoginPage = React.lazy(() => import('@/routes/UnsubscribeLoginPage').then(m => ({default: m.UnsubscribeLoginPage})));
const LoginLinkPage = React.lazy(() => import('@/routes/LoginLinkPage').then(m => ({default: m.LoginLinkPage})));
const EmailAuthLinkPage = React.lazy(() => import('@/routes/EmailAuthLinkPage').then(m => ({default: m.EmailAuthLinkPage})));
const ImpersonateLoginPage = React.lazy(() => import('@/routes/ImpersonateLoginPage').then(m => ({default: m.ImpersonateLoginPage})));

export const router = createBrowserRouter([
    // Block preview route — rendered in iframe for admin live preview, no menu/footer
    {path: '/_block-preview', element: <BlockPreviewPage/>},
    // Public embed widget — rendered in third-party iframe, no menu/footer
    {path: '/_embed/:embedSlug', element: <EmbedBlockPage/>},
    {
        path: '/',
        element: <Layout/>,
        children: [

            // support rout pointer for support old url
            {path: 'membership/events', element: lazyRoute(<EventRegistrationPage/>)},

            // homepage — resolved dynamically from SiteSettings.homepage_route
            {index: true, element: <HomepageResolver/>},

            // news pages
            {path: 'news', element: lazyRoute(<NewsPage/>)},
            {path: 'news/:id', element: lazyRoute(<NewsDetailPage/>)},

            // project pages (plain CMS routes like /projects, /sample-proposals
            {path: 'current-projects', element: lazyRoute(<ProjectsPage/>)},
            {path: 'presenting-teams', element: lazyRoute(<PresentingTeamsPage/>)},
            {path: 'past-projects', element: lazyRoute(<PastProjectsPage/>)},
            {path: 'past-projects/:shareId', element: lazyRoute(<PastProjectsPage/>)},
            {path: 'projects/:id', element: lazyRoute(<ProjectDetailPage/>)},

            // event pages (plain CMS routes like /event, /past-events are served
            // by the catch-all CMS route below)
            {path: 'event-registration', element: lazyRoute(<EventRegistrationPage/>)},
            {path: 'events/:eventSlug', element: lazyRoute(<EventArchivePage/>)},
            {path: 'schedule', element: lazyRoute(<SchedulePage/>)},
            {path: 'acknowledgement', element: lazyRoute(<AcknowledgementPage/>)},

            // Subscribe
            {path: 'subscribe', element: lazyRoute(<SubscribePage/>)},

            // Auto-login from email links
            {path: 'login-link', element: lazyRoute(<LoginLinkPage/>)},
            // Legacy aliases: previously-sent emails point at /magic-login (still
            // valid tokens) and /ticket-login (tokens already invalidated).
            {path: 'magic-login', element: <LegacyLoginLinkRedirect/>},
            {path: 'ticket-login', element: <LegacyLoginLinkRedirect/>},
            {path: 'unsubscribe-login', element: lazyRoute(<UnsubscribeLoginPage/>)},
            {path: 'email-auth-link', element: lazyRoute(<EmailAuthLinkPage/>)},
            {path: 'impersonate-login', element: lazyRoute(<ImpersonateLoginPage/>)},

            // Convenience redirects
            {path: 'profile', element: <Navigate to="/account" replace/>},

            // Auth pages
            {path: 'login', element: lazyRoute(<LoginPage/>)},
            {path: 'register', element: lazyRoute(<RegisterPage/>)},
            {path: 'forgot-password', element: lazyRoute(<ForgotPasswordPage/>)},
            {path: 'verify-email', element: lazyRoute(<VerifyEmailPage/>)},
            {path: 'complete-profile', element: lazyRoute(<CompleteProfilePage/>)},

            // Account management
            {path: 'account', element: lazyRoute(<AccountPage/>)},

            // Catch-all CMS route
            {path: '*', element: <CMSPageComponent/>},
        ],
    },
]);
