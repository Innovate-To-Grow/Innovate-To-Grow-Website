import { createBrowserRouter } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { Home } from '../pages/Home';
import { ProjectsPage } from '../pages/ProjectsPage';
import { PageContent } from '../components/PageContent/PageContent';
import { EventPage, SchedulePage } from '../components/Event';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'event', element: <EventPage /> },
      { path: 'schedule', element: <SchedulePage /> },
      { path: 'projects', element: <ProjectsPage /> },
      // Catch-all route for CMS-driven pages (e.g., /about, /about/team)
      { path: '*', element: <PageContent /> },
    ],
  },
]);
