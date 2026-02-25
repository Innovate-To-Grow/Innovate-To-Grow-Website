import { createBrowserRouter } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { Home } from '../pages/Home';
import { PageContent } from '../components/PageContent/PageContent';
import { EventPage } from '../components/Event';
import { VerifyEmailPage } from '../components/Auth';
import { PreviewPage } from '../pages/Preview/PreviewPage';
import { TokenPreviewPage } from '../pages/Preview/TokenPreviewPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'event', element: <EventPage /> },
      // Email verification route
      { path: 'verify-email/:token', element: <VerifyEmailPage /> },
      // Live preview route (cache-based, requires admin session)
      { path: 'preview', element: <PreviewPage /> },
      // Token-based shareable preview route (database-backed, no auth required)
      { path: 'preview/:token', element: <TokenPreviewPage /> },
      // Catch-all route for CMS-driven pages (e.g., /about, /about/team)
      { path: '*', element: <PageContent /> },
    ],
  },
]);
