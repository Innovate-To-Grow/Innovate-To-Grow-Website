import React from 'react';
import {createBrowserRouter, Navigate} from 'react-router-dom';
import {Layout} from '../components/Layout';
import {CMSPageComponent} from '../components/CMS';
import {HomepageResolver} from './HomepageResolver';
import {BlockPreviewPage} from '../components/CMS/BlockPreviewPage';

// Auth pages (lazy)
const LoginPage = React.lazy(() => import('../components/Auth/pages/LoginPage').then(m => ({default: m.LoginPage})));
const RegisterPage = React.lazy(() => import('../components/Auth/pages/RegisterPage').then(m => ({default: m.RegisterPage})));
const AccountPage = React.lazy(() => import('../components/Auth/pages/AccountPage').then(m => ({default: m.AccountPage})));
const CompleteProfilePage = React.lazy(() => import('../components/Auth/pages/CompleteProfilePage').then(m => ({default: m.CompleteProfilePage})));
const ForgotPasswordPage = React.lazy(() => import('../components/Auth/pages/ForgotPasswordPage').then(m => ({default: m.ForgotPasswordPage})));
const VerifyEmailPage = React.lazy(() => import('../components/Auth/pages/VerifyEmailPage').then(m => ({default: m.VerifyEmailPage})));

// Content pages (lazy) — only non-CMS pages
const NewsPage = React.lazy(() => import('../pages/NewsPage').then(m => ({default: m.NewsPage})));
const NewsDetailPage = React.lazy(() => import('../pages/NewsDetailPage').then(m => ({default: m.NewsDetailPage})));
const ProjectsPage = React.lazy(() => import('../pages/ProjectsPage').then(m => ({default: m.ProjectsPage})));
const PastProjectsPage = React.lazy(() => import('../pages/PastProjectsPage').then(m => ({default: m.PastProjectsPage})));
const ProjectDetailPage = React.lazy(() => import('../pages/ProjectDetailPage').then(m => ({default: m.ProjectDetailPage})));
const SchedulePage = React.lazy(() => import('../pages/SchedulePage').then(m => ({default: m.SchedulePage})));
const AcknowledgementPage = React.lazy(() => import('../pages/AcknowledgementPage').then(m => ({default: m.AcknowledgementPage})));
const EventArchivePage = React.lazy(() => import('../pages/EventArchivePage').then(m => ({default: m.EventArchivePage})));
const EventRegistrationPage = React.lazy(() => import('../pages/EventRegistrationPage').then(m => ({default: m.EventRegistrationPage})));
const TicketLoginPage = React.lazy(() => import('../pages/TicketLoginPage').then(m => ({default: m.TicketLoginPage})));
const SubscribePage = React.lazy(() => import('../pages/SubscribePage').then(m => ({default: m.SubscribePage})));
const UnsubscribeLoginPage = React.lazy(() => import('../pages/UnsubscribeLoginPage').then(m => ({default: m.UnsubscribeLoginPage})));
const MagicLoginPage = React.lazy(() => import('../pages/MagicLoginPage').then(m => ({default: m.MagicLoginPage})));
const ImpersonateLoginPage = React.lazy(() => import('../pages/ImpersonateLoginPage').then(m => ({default: m.ImpersonateLoginPage})));

export const router = createBrowserRouter([
    // Block preview route — rendered in iframe, no menu/footer
    {path: '/_block-preview', element: <BlockPreviewPage/>},
    {
        path: '/',
        element: <Layout/>,
        children: [

            // support rout pointer for support old url
            {path: 'membership/events', element: <EventRegistrationPage/>},

            // homepage — resolved dynamically from SiteSettings.homepage_route
            {index: true, element: <HomepageResolver/>},

            // news pages
            {path: 'news', element: <NewsPage/>},
            {path: 'news/:id', element: <NewsDetailPage/>},

            // project pages
            {path: 'projects', element: <CMSPageComponent/>},
            {path: 'current-projects', element: <ProjectsPage/>},
            {path: 'past-projects', element: <PastProjectsPage/>},
            {path: 'past-projects/:shareId', element: <PastProjectsPage/>},
            {path: 'projects/past', element: <Navigate to="/past-projects" replace/>},
            {path: 'projects/:id', element: <ProjectDetailPage/>},
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
            {path: 'event-registration', element: <EventRegistrationPage/>},
            {path: 'events/:eventSlug', element: <EventArchivePage/>},
            {path: 'schedule', element: <SchedulePage/>},
            {path: 'past-events', element: <CMSPageComponent/>},
            {path: 'post-event-home', element: <CMSPageComponent/>},
            {path: 'acknowledgement', element: <AcknowledgementPage/>},

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
            {path: '2025-fall-event', element: <Navigate to="/events/2025-fall" replace/>},
            {path: '2025-spring-event', element: <Navigate to="/events/2025-spring" replace/>},
            {path: '2024-fall-event', element: <Navigate to="/events/2024-fall" replace/>},
            {path: '2024-spring-event', element: <Navigate to="/events/2024-spring" replace/>},
            {path: '2023-fall-event', element: <Navigate to="/events/2023-fall" replace/>},
            {path: '2023-spring-event', element: <Navigate to="/events/2023-spring" replace/>},
            {path: '2022-fall-event', element: <Navigate to="/events/2022-fall" replace/>},
            {path: '2022-spring-event', element: <Navigate to="/events/2022-spring" replace/>},
            {path: '2021-fall-event', element: <Navigate to="/events/2021-fall" replace/>},
            {path: '2021-spring-event', element: <Navigate to="/events/2021-spring" replace/>},
            {path: '2020-fall-post-event', element: <Navigate to="/events/2020-fall" replace/>},

            // Subscribe
            {path: 'subscribe', element: <SubscribePage/>},

            // Auto-login from email links
            {path: 'ticket-login', element: <TicketLoginPage/>},
            {path: 'unsubscribe-login', element: <UnsubscribeLoginPage/>},
            {path: 'magic-login', element: <MagicLoginPage/>},
            {path: 'impersonate-login', element: <ImpersonateLoginPage/>},

            // Convenience redirects
            {path: 'profile', element: <Navigate to="/account" replace/>},

            // Auth pages
            {path: 'login', element: <LoginPage/>},
            {path: 'register', element: <RegisterPage/>},
            {path: 'forgot-password', element: <ForgotPasswordPage/>},
            {path: 'verify-email', element: <VerifyEmailPage/>},
            {path: 'complete-profile', element: <CompleteProfilePage/>},

            // Account management
            {path: 'account', element: <AccountPage/>},

            // Catch-all CMS route
            {path: '*', element: <CMSPageComponent/>},
        ],
    },
]);
