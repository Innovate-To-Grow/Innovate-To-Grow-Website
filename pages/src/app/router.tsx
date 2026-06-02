import React, {Suspense, type ReactElement} from 'react';
import {createBrowserRouter, Navigate} from 'react-router-dom';
import {Layout} from '@/features/layout';
import {CMSPageComponent} from '@/features/cms';
import {HomepageResolver} from './HomepageResolver';
import {BlockPreviewPage} from '@/features/cms/components/BlockPreviewPage';
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
const EventRegistrationPage = React.lazy(() => import('@/routes/EventRegistrationPage').then(m => ({default: m.EventRegistrationPage})));
const TicketLoginPage = React.lazy(() => import('@/routes/TicketLoginPage').then(m => ({default: m.TicketLoginPage})));
const SubscribePage = React.lazy(() => import('@/routes/SubscribePage').then(m => ({default: m.SubscribePage})));
const UnsubscribeLoginPage = React.lazy(() => import('@/routes/UnsubscribeLoginPage').then(m => ({default: m.UnsubscribeLoginPage})));
const MagicLoginPage = React.lazy(() => import('@/routes/MagicLoginPage').then(m => ({default: m.MagicLoginPage})));
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

            // project pages
            {path: 'projects', element: <CMSPageComponent/>},
            {path: 'current-projects', element: lazyRoute(<ProjectsPage/>)},
            {path: 'presenting-teams', element: lazyRoute(<PresentingTeamsPage/>)},
            {path: 'past-projects', element: lazyRoute(<PastProjectsPage/>)},
            {path: 'past-projects/:shareId', element: lazyRoute(<PastProjectsPage/>)},
            {path: 'projects/past', element: <Navigate to="/past-projects" replace/>},
            {path: 'projects/:id', element: lazyRoute(<ProjectDetailPage/>)},
            {path: 'sample-proposals', element: <CMSPageComponent/>},

            // about pages
            {path: 'about', element: <CMSPageComponent/>},
            {path: 'engineering-capstone', element: <CMSPageComponent/>},
            {path: 'software-capstone', element: <CMSPageComponent/>},
            {path: 'about-engsl', element: <CMSPageComponent/>},
            {path: 'project-submission', element: <CMSPageComponent/>},
            {path: 'partnership', element: <CMSPageComponent/>},
            {path: 'sponsorship', element: <CMSPageComponent/>},
            {path: 'sponsor-acknowledgement', element: <CMSPageComponent/>},
            {path: 'sponsors/2014', element: <CMSPageComponent/>},
            {path: 'sponsors/2015', element: <CMSPageComponent/>},

            // judge & attendee pages
            {path: 'judges', element: <CMSPageComponent/>},
            {path: 'attendees', element: <CMSPageComponent/>},
            {path: 'judging', element: <CMSPageComponent/>},

            // event pages
            {path: 'event', element: <CMSPageComponent/>},
            {path: 'event-registration', element: lazyRoute(<EventRegistrationPage/>)},
            {path: 'schedule', element: lazyRoute(<SchedulePage/>)},
            {path: 'past-events', element: <CMSPageComponent/>},
            {path: 'post-event-home', element: <CMSPageComponent/>},
            {path: 'acknowledgement', element: lazyRoute(<AcknowledgementPage/>)},

            // student pages
            {path: 'students', element: <CMSPageComponent/>},
            {path: 'student-agreement', element: <CMSPageComponent/>},
            {path: 'event-preparation', element: <CMSPageComponent/>},
            {path: 'video-preparation', element: <CMSPageComponent/>},
            {path: 'purchasing-reimbursement', element: <CMSPageComponent/>},
            {path: 'ferpa', element: <CMSPageComponent/>},
            {path: 'privacy', element: <CMSPageComponent/>},
            {path: 'faqs', element: <CMSPageComponent/>},
            {path: 'contact-us', element: <CMSPageComponent/>},
            {path: 'I2G-student-agreement', element: <Navigate to="/student-agreement" replace/>},
            {path: 'i2g-students-preparation', element: <Navigate to="/event-preparation" replace/>},
            {path: 'capstone-purchasing-reimbursement', element: <Navigate to="/purchasing-reimbursement" replace/>},
            {path: 'about_EngSL', element: <Navigate to="/about-engsl" replace/>},
            {path: 'FAQs', element: <Navigate to="/faqs" replace/>},
            {path: 'I2G-project-sponsor-acknowledgement', element: <Navigate to="/sponsor-acknowledgement" replace/>},
            {path: '2014-sponsors', element: <Navigate to="/sponsors/2014" replace/>},
            {path: '2015-sponsors', element: <Navigate to="/sponsors/2015" replace/>},
            // Per-semester past-event pages (2020–2024) are now CMS pages served by the
            // catch-all below at their canonical paths (e.g. /2024-fall-event).

            // Subscribe
            {path: 'subscribe', element: lazyRoute(<SubscribePage/>)},

            // Auto-login from email links
            {path: 'ticket-login', element: lazyRoute(<TicketLoginPage/>)},
            {path: 'unsubscribe-login', element: lazyRoute(<UnsubscribeLoginPage/>)},
            {path: 'magic-login', element: lazyRoute(<MagicLoginPage/>)},
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
