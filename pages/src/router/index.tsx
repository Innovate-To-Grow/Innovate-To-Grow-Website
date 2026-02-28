import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { Home } from '../pages/Home';
import { PageContent } from '../components/PageContent/PageContent';
import { EventPage } from '../components/Event';
import {
  LoginPage,
  RegisterPage,
  VerifyPending,
  AccountPage,
} from '../components/Auth';
import { PreviewPage } from '../pages/Preview/PreviewPage';
import { TokenPreviewPage } from '../pages/Preview/TokenPreviewPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'event', element: <EventPage /> },
      // Convenience redirects
      { path: 'events', element: <Navigate to="/event" replace /> },
      { path: 'profile', element: <Navigate to="/account" replace /> },
      // Auth pages
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },
      { path: 'verify-pending', element: <VerifyPending /> },
      // Live preview route (cache-based, requires admin session)
      { path: 'preview', element: <PreviewPage /> },
      // Token-based shareable preview route (database-backed, no auth required)
      { path: 'preview/:token', element: <TokenPreviewPage /> },
      // Account management
      { path: 'account', element: <AccountPage /> },
      // Catch-all route for CMS-driven pages (e.g., /about, /about/team)
      { path: '*', element: <PageContent /> },
    ],
  },
]);
