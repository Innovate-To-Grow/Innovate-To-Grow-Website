import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { EventPage } from '../components/Event';
import {
  LoginPage,
  RegisterPage,
  AccountPage,
  ForgotPasswordPage,
  VerifyEmailPage,
} from '../components/Auth';
import { NewsPage } from '../pages/NewsPage';
import { NewsDetailPage } from '../pages/NewsDetailPage';
import { ProjectsPage } from '../pages/ProjectsPage';
import { PastProjectsPage } from '../pages/PastProjectsPage';
import { ProjectDetailPage } from '../pages/ProjectDetailPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { path: 'event', element: <EventPage /> },
      { path: 'news', element: <NewsPage /> },
      { path: 'news/:id', element: <NewsDetailPage /> },
      { path: 'projects', element: <ProjectsPage /> },
      { path: 'past-projects', element: <PastProjectsPage /> },
      { path: 'projects/past', element: <Navigate to="/past-projects" replace /> },
      { path: 'projects/:id', element: <ProjectDetailPage /> },
      // Convenience redirects
      { path: 'events', element: <Navigate to="/event" replace /> },
      { path: 'profile', element: <Navigate to="/account" replace /> },
      // Auth pages
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },
      { path: 'forgot-password', element: <ForgotPasswordPage /> },
      { path: 'verify-email', element: <VerifyEmailPage /> },
      // Account management
      { path: 'account', element: <AccountPage /> },
    ],
  },
]);
