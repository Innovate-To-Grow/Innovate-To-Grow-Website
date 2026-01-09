import { createBrowserRouter } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { Home } from '../pages/Home';
import { ProjectsPage } from '../pages/ProjectsPage';
import { ArchivePage } from '../pages/ArchivePage';
import { PastEventsPage } from '../pages/PastEventsPage';
import { PastProjectsPage } from '../pages/PastProjectsPage';
import { HomePostEvent } from '../pages/HomePostEvent';
import { HomePreEvent } from '../pages/HomePreEvent';
import { HomeDuringSemester } from '../pages/HomeDuringSemester';
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
      { path: 'past-projects', element: <PastProjectsPage /> },
      { path: 'past-projects/shared/:uuid', element: <PastProjectsPage /> },
      { path: 'home-post-event', element: <HomePostEvent /> },
      { path: 'home-pre-event', element: <HomePreEvent /> },
      { path: 'home-during-semester', element: <HomeDuringSemester /> },
      // Catch-all route for CMS-driven pages (e.g., /about, /about/team)
      { path: '*', element: <PageContent /> },
    ],
  },
]);
