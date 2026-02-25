import { createBrowserRouter } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { Home } from '../pages/Home';
import { PageContent } from '../components/PageContent/PageContent';
import { EventPage } from '../components/Event';
import { VerifyEmailPage, AccountPage } from '../components/Auth';
import { PreviewPage } from '../pages/Preview/PreviewPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'event', element: <EventPage /> },
      // Email verification route
      { path: 'verify-email/:token', element: <VerifyEmailPage /> },
      // Preview route
      { path: 'preview', element: <PreviewPage /> },
      // Account management
      { path: 'account', element: <AccountPage /> },
      // Catch-all route for CMS-driven pages (e.g., /about, /about/team)
      { path: '*', element: <PageContent /> },
    ],
  },
]);
