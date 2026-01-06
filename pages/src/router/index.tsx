import { createBrowserRouter } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { Home } from '../pages/Home';
import { ProjectsPage } from '../pages/ProjectsPage';
import { ArchivePage } from '../pages/ArchivePage';
import { PastEventsPage } from '../pages/PastEventsPage';
import { HomePostEvent } from '../pages/HomePostEvent';
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
      { path: 'archive/:slug', element: <ArchivePage /> },
      { path: 'past-events', element: <PastEventsPage /> },
      { path: 'home-post-event', element: <HomePostEvent /> },
      // Catch-all route for CMS-driven pages (e.g., /about, /about/team)
      { path: '*', element: <PageContent /> },
    ],
  },
]);
