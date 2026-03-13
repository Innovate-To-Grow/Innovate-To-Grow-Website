import React, {Suspense} from 'react';
import {createBrowserRouter, Navigate} from 'react-router-dom';
import {Layout} from '../components/Layout';
import {useLayout} from '../components/Layout/LayoutProvider/context';

// Auth pages (lazy)
const LoginPage = React.lazy(() => import('../components/Auth/pages/LoginPage').then(m => ({default: m.LoginPage})));
const RegisterPage = React.lazy(() => import('../components/Auth/pages/RegisterPage').then(m => ({default: m.RegisterPage})));
const AccountPage = React.lazy(() => import('../components/Auth/pages/AccountPage').then(m => ({default: m.AccountPage})));
const CompleteProfilePage = React.lazy(() => import('../components/Auth/pages/CompleteProfilePage').then(m => ({default: m.CompleteProfilePage})));
const ForgotPasswordPage = React.lazy(() => import('../components/Auth/pages/ForgotPasswordPage').then(m => ({default: m.ForgotPasswordPage})));
const VerifyEmailPage = React.lazy(() => import('../components/Auth/pages/VerifyEmailPage').then(m => ({default: m.VerifyEmailPage})));

// Content pages (lazy)
const HomePage = React.lazy(() => import('../pages/HomePage').then(m => ({default: m.HomePage})));
const NewsPage = React.lazy(() => import('../pages/NewsPage').then(m => ({default: m.NewsPage})));
const NewsDetailPage = React.lazy(() => import('../pages/NewsDetailPage').then(m => ({default: m.NewsDetailPage})));
const ProjectsPage = React.lazy(() => import('../pages/ProjectsPage').then(m => ({default: m.ProjectsPage})));
const PastProjectsPage = React.lazy(() => import('../pages/PastProjectsPage').then(m => ({default: m.PastProjectsPage})));
const ProjectDetailPage = React.lazy(() => import('../pages/ProjectDetailPage').then(m => ({default: m.ProjectDetailPage})));
const ProjectSubmissionPage = React.lazy(() => import('../pages/ProjectSubmissionPage').then(m => ({default: m.ProjectSubmissionPage})));
const SampleProposalsPage = React.lazy(() => import('../pages/SampleProposalsPage').then(m => ({default: m.SampleProposalsPage})));
const ProjectsHubPage = React.lazy(() => import('../pages/ProjectsHubPage').then(m => ({default: m.ProjectsHubPage})));
const AboutPage = React.lazy(() => import('../pages/AboutPage').then(m => ({default: m.AboutPage})));
const EngineeringCapstonePage = React.lazy(() => import('../pages/EngineeringCapstonePage').then(m => ({default: m.EngineeringCapstonePage})));
const SoftwareCapstonePage = React.lazy(() => import('../pages/SoftwareCapstonePage').then(m => ({default: m.SoftwareCapstonePage})));
const NotFoundPage = React.lazy(() => import('../pages/NotFoundPage').then(m => ({default: m.NotFoundPage})));
const StudentsPage = React.lazy(() => import('../pages/StudentsPage').then(m => ({default: m.StudentsPage})));
const StudentAgreementPage = React.lazy(() => import('../pages/StudentAgreementPage').then(m => ({default: m.StudentAgreementPage})));
const EventPreparationPage = React.lazy(() => import('../pages/EventPreparationPage').then(m => ({default: m.EventPreparationPage})));
const VideoPreparationPage = React.lazy(() => import('../pages/VideoPreparationPage').then(m => ({default: m.VideoPreparationPage})));
const PurchasingReimbursementPage = React.lazy(() => import('../pages/PurchasingReimbursementPage').then(m => ({default: m.PurchasingReimbursementPage})));
const FerpaAgreementPage = React.lazy(() => import('../pages/FerpaAgreementPage').then(m => ({default: m.FerpaAgreementPage})));
const PrivacyPolicyPage = React.lazy(() => import('../pages/PrivacyPolicyPage').then(m => ({default: m.PrivacyPolicyPage})));
const EngSLPage = React.lazy(() => import('../pages/EngSLPage').then(m => ({default: m.EngSLPage})));
const PartnershipPage = React.lazy(() => import('../pages/PartnershipPage').then(m => ({default: m.PartnershipPage})));
const SponsorAcknowledgementPage = React.lazy(() => import('../pages/SponsorAcknowledgementPage').then(m => ({default: m.SponsorAcknowledgementPage})));
const SponsorshipPage = React.lazy(() => import('../pages/SponsorshipPage').then(m => ({default: m.SponsorshipPage})));
const FaqPage = React.lazy(() => import('../pages/FaqPage').then(m => ({default: m.FaqPage})));
const ContactUsPage = React.lazy(() => import('../pages/ContactUsPage').then(m => ({default: m.ContactUsPage})));
const JudgesPage = React.lazy(() => import('../pages/JudgesPage').then(m => ({default: m.JudgesPage})));
const AttendeesPage = React.lazy(() => import('../pages/AttendeesPage').then(m => ({default: m.AttendeesPage})));
const JudgingPage = React.lazy(() => import('../pages/JudgingPage').then(m => ({default: m.JudgingPage})));
const SponsorsArchivePage = React.lazy(() => import('../pages/SponsorsArchivePage').then(m => ({default: m.SponsorsArchivePage})));
const EventPage = React.lazy(() => import('../pages/EventPage').then(m => ({default: m.EventPage})));
const SchedulePage = React.lazy(() => import('../pages/SchedulePage').then(m => ({default: m.SchedulePage})));
const ProjectsTeamsPage = React.lazy(() => import('../pages/ProjectsTeamsPage').then(m => ({default: m.ProjectsTeamsPage})));
const PastEventsPage = React.lazy(() => import('../pages/PastEventsPage').then(m => ({default: m.PastEventsPage})));
const AcknowledgementPage = React.lazy(() => import('../pages/AcknowledgementPage').then(m => ({default: m.AcknowledgementPage})));
const EventArchivePage = React.lazy(() => import('../pages/EventArchivePage').then(m => ({default: m.EventArchivePage})));

// Map route paths to their lazy page components for dynamic homepage resolution
const PAGE_REGISTRY: Record<string, React.LazyExoticComponent<React.ComponentType>> = {
    '/about': AboutPage,
    '/news': NewsPage,
    '/faqs': FaqPage,
    '/contact-us': ContactUsPage,
    '/privacy': PrivacyPolicyPage,
    '/ferpa': FerpaAgreementPage,
    '/engineering-capstone': EngineeringCapstonePage,
    '/software-capstone': SoftwareCapstonePage,
    '/about-engsl': EngSLPage,
    '/projects': ProjectsHubPage,
    '/current-projects': ProjectsPage,
    '/past-projects': PastProjectsPage,
    '/project-submission': ProjectSubmissionPage,
    '/sample-proposals': SampleProposalsPage,
    '/projects-teams': ProjectsTeamsPage,
    '/students': StudentsPage,
    '/student-agreement': StudentAgreementPage,
    '/event-preparation': EventPreparationPage,
    '/video-preparation': VideoPreparationPage,
    '/purchasing-reimbursement': PurchasingReimbursementPage,
    '/event': EventPage,
    '/schedule': SchedulePage,
    '/past-events': PastEventsPage,
    '/judges': JudgesPage,
    '/attendees': AttendeesPage,
    '/judging': JudgingPage,
    '/partnership': PartnershipPage,
    '/sponsorship': SponsorshipPage,
    '/sponsor-acknowledgement': SponsorAcknowledgementPage,
    '/acknowledgement': AcknowledgementPage,
};

/** Renders the admin-selected page at "/" or falls back to HomePage. */
const HomepageResolver = () => {
    const {homepage_route, state} = useLayout();

    if (state === 'loading') {
        return null;
    }

    if (!homepage_route || homepage_route === '/') {
        return <HomePage/>;
    }

    const PageComponent = PAGE_REGISTRY[homepage_route];
    if (!PageComponent) {
        return <HomePage/>;
    }

    return (
        <Suspense fallback={null}>
            <PageComponent/>
        </Suspense>
    );
};

export const router = createBrowserRouter([
    {
        path: '/',
        element: <Layout/>,
        children: [
            // homepage — resolved dynamically from SiteSettings.homepage_route
            {index: true, element: <HomepageResolver/>},

            // news pages
            {path: 'news', element: <NewsPage/>},
            {path: 'news/:id', element: <NewsDetailPage/>},

            // project pages
            {path: 'projects', element: <ProjectsHubPage/>},
            {path: 'current-projects', element: <ProjectsPage/>},
            {path: 'past-projects', element: <PastProjectsPage/>},
            {path: 'projects/past', element: <Navigate to="/past-projects" replace/>},
            {path: 'projects/:id', element: <ProjectDetailPage/>},
            {path: 'sample-proposals', element: <SampleProposalsPage/>},

            // about pages
            {path: 'about', element: <AboutPage/>},
            {path: 'engineering-capstone', element: <EngineeringCapstonePage/>},
            {path: 'software-capstone', element: <SoftwareCapstonePage/>},
            {path: 'about-engsl', element: <EngSLPage/>},
            {path: 'project-submission', element: <ProjectSubmissionPage/>},
            {path: 'partnership', element: <PartnershipPage/>},
            {path: 'sponsorship', element: <SponsorshipPage/>},
            {path: 'sponsor-acknowledgement', element: <SponsorAcknowledgementPage/>},
            {path: 'sponsors/:year', element: <SponsorsArchivePage/>},

            // judge & attendee pages
            {path: 'judges', element: <JudgesPage/>},
            {path: 'attendees', element: <AttendeesPage/>},
            {path: 'judging', element: <JudgingPage/>},

            // event pages
            {path: 'event', element: <EventPage/>},
            {path: 'events/:eventSlug', element: <EventArchivePage/>},
            {path: 'schedule', element: <SchedulePage/>},
            {path: 'projects-teams', element: <ProjectsTeamsPage/>},
            {path: 'past-events', element: <PastEventsPage/>},
            {path: 'acknowledgement', element: <AcknowledgementPage/>},

            // student pages
            {path: 'students', element: <StudentsPage/>},
            {path: 'student-agreement', element: <StudentAgreementPage/>},
            {path: 'event-preparation', element: <EventPreparationPage/>},
            {path: 'video-preparation', element: <VideoPreparationPage/>},
            {path: 'purchasing-reimbursement', element: <PurchasingReimbursementPage/>},
            {path: 'ferpa', element: <FerpaAgreementPage/>},
            {path: 'privacy', element: <PrivacyPolicyPage/>},
            {path: 'faqs', element: <FaqPage/>},
            {path: 'contact-us', element: <ContactUsPage/>},
            {path: 'I2G-student-agreement', element: <Navigate to="/student-agreement" replace/>},
            {path: 'i2g-students-preparation', element: <Navigate to="/event-preparation" replace/>},
            {path: 'capstone-purchasing-reimbursement', element: <Navigate to="/purchasing-reimbursement" replace/>},
            {path: 'about_EngSL', element: <Navigate to="/about-engsl" replace/>},
            {path: 'FAQs', element: <Navigate to="/faqs" replace/>},
            {path: 'I2G-project-sponsor-acknowledgement', element: <Navigate to="/sponsor-acknowledgement" replace/>},
            {path: '2014-sponsors', element: <Navigate to="/sponsors/2014" replace/>},
            {path: '2015-sponsors', element: <Navigate to="/sponsors/2015" replace/>},
            {path: 'home-post-event', element: <Navigate to="/" replace/>},
            {path: 'home-during-event', element: <Navigate to="/" replace/>},
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

            // Catch-all 404
            {path: '*', element: <NotFoundPage/>},
        ],
    },
]);
