import {createBrowserRouter, Navigate} from 'react-router-dom';
import {Layout} from '../components/Layout';
import {
    LoginPage,
    RegisterPage,
    AccountPage,
    ForgotPasswordPage,
    VerifyEmailPage,
} from '../components/Auth';
import {NewsPage} from '../pages/NewsPage';
import {NewsDetailPage} from '../pages/NewsDetailPage';
import {ProjectsPage} from '../pages/ProjectsPage';
import {PastProjectsPage} from '../pages/PastProjectsPage';
import {ProjectDetailPage} from '../pages/ProjectDetailPage';
import {ProjectSubmissionPage} from '../pages/ProjectSubmissionPage';
import {SampleProposalsPage} from '../pages/SampleProposalsPage';
import {ProjectsHubPage} from '../pages/ProjectsHubPage';
import {AboutPage} from '../pages/AboutPage';
import {EngineeringCapstonePage} from '../pages/EngineeringCapstonePage';
import {SoftwareCapstonePage} from '../pages/SoftwareCapstonePage';
import {NotFoundPage} from '../pages/NotFoundPage';
import {StudentsPage} from '../pages/StudentsPage';
import {StudentAgreementPage} from '../pages/StudentAgreementPage';
import {EventPreparationPage} from '../pages/EventPreparationPage';
import {VideoPreparationPage} from '../pages/VideoPreparationPage';
import {PurchasingReimbursementPage} from '../pages/PurchasingReimbursementPage';
import {FerpaAgreementPage} from '../pages/FerpaAgreementPage';

export const router = createBrowserRouter([
    {
        path: '/',
        element: <Layout/>,
        children: [
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
            {path: 'project-submission', element: <ProjectSubmissionPage/>},

            // student pages
            {path: 'students', element: <StudentsPage/>},
            {path: 'student-agreement', element: <StudentAgreementPage/>},
            {path: 'event-preparation', element: <EventPreparationPage/>},
            {path: 'video-preparation', element: <VideoPreparationPage/>},
            {path: 'purchasing-reimbursement', element: <PurchasingReimbursementPage/>},
            {path: 'ferpa', element: <FerpaAgreementPage/>},
            {path: 'I2G-student-agreement', element: <Navigate to="/student-agreement" replace/>},
            {path: 'i2g-students-preparation', element: <Navigate to="/event-preparation" replace/>},
            {path: 'capstone-purchasing-reimbursement', element: <Navigate to="/purchasing-reimbursement" replace/>},

            // Convenience redirects
            {path: 'profile', element: <Navigate to="/account" replace/>},

            // Auth pages
            {path: 'login', element: <LoginPage/>},
            {path: 'register', element: <RegisterPage/>},
            {path: 'forgot-password', element: <ForgotPasswordPage/>},
            {path: 'verify-email', element: <VerifyEmailPage/>},

            // Account management
            {path: 'account', element: <AccountPage/>},

            // Catch-all 404
            {path: '*', element: <NotFoundPage/>},
        ],
    },
]);
