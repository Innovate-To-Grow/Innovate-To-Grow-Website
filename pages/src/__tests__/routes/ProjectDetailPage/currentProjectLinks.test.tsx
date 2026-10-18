import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter, Route, Routes} from 'react-router';

import {ProjectDetailPage} from '@/routes/ProjectDetailPage/ProjectDetailPage';
import {ProjectsPage} from '@/routes/ProjectsPage/ProjectsPage';
import {PresentingTeamsPage} from '@/routes/PresentingTeamsPage/PresentingTeamsPage';
import {fetchProjectDetail} from '@/features/projects/api';
import {fetchCurrentSchedule} from '@/features/events/api';
import {
  DASHBOARD_PROJECT_ID,
  HVAC_PROJECT_ID,
  WING_PROJECT_ID,
  currentSchedulePayload,
} from '@/__tests__/features/projects/fixtures/currentSchedule';

// Only the network is mocked: the list pages, their row links and the detail page run for real, against the
// production schedule shape. As in production, the archive detail endpoint answers 404 for every id the
// schedule hands out (they are CurrentProject ids, not archive Project ids).
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: vi.fn(),
}));

vi.mock('@/features/events/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/events/api')>()),
  fetchCurrentSchedule: vi.fn(),
}));

const renderSite = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/current-projects" element={<ProjectsPage />} />
        <Route path="/presenting-teams" element={<PresentingTeamsPage />} />
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

const desktopTable = () => document.querySelector('.project-grid-table-wrap') as HTMLElement;

describe('current project links', () => {
  beforeEach(() => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    vi.mocked(fetchCurrentSchedule).mockReset();
    vi.mocked(fetchCurrentSchedule).mockResolvedValue(currentSchedulePayload());
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValue(
      Object.assign(new Error('Request failed with status code 404'), {response: {status: 404}}),
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('opens a populated project page from a Current Projects title', async () => {
    renderSite('/current-projects');

    await screen.findByRole('heading', {level: 1, name: 'Current Projects'});
    const title = within(desktopTable()).getByRole('link', {name: 'ASHRAE HVAC Design Calculations'});
    expect(title).toHaveAttribute('href', `/projects/${HVAC_PROJECT_ID}`);
    fireEvent.click(title);

    expect(
      await screen.findByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'}),
    ).toBeInTheDocument();
    expect(screen.getByText('Engineering Capstone · Spring 2026')).toBeInTheDocument();
    expect(screen.getByText(/^This project aimed to design a complete HVAC system/)).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 2, name: 'Team members'})).toBeInTheDocument();
    expect(screen.getAllByRole('link', {name: /back to current projects/i})[0]).toHaveAttribute(
      'href',
      '/current-projects',
    );
    expect(screen.queryByText("We couldn't find this project")).toBeNull();
  });

  it('opens the page of a team that is not presenting from Current Projects', async () => {
    renderSite('/current-projects');

    await screen.findByRole('heading', {level: 1, name: 'Current Projects'});
    const title = within(desktopTable()).getByRole('link', {
      name: 'Distributed-Flapping Wing with Glide-Lock Mechanism',
    });
    expect(title).toHaveAttribute('href', `/projects/${WING_PROJECT_ID}`);
    fireEvent.click(title);

    expect(
      await screen.findByRole('heading', {level: 1, name: 'Distributed-Flapping Wing with Glide-Lock Mechanism'}),
    ).toBeInTheDocument();
    expect(screen.getByText('Abstract-201')).toBeInTheDocument();
  });

  it('opens a populated project page from the "Open the project page" link on Presenting Teams', async () => {
    renderSite('/presenting-teams');

    await screen.findByRole('heading', {level: 1, name: 'Presenting Teams'});
    const table = desktopTable();
    const row = within(table).getByRole('link', {name: 'Sustainability Dashboard'}).closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', {name: /details/i}));
    const openPage = within(table).getByRole('link', {name: 'Open the project page'});
    expect(openPage).toHaveAttribute('href', `/projects/${DASHBOARD_PROJECT_ID}`);
    fireEvent.click(openPage);

    expect(await screen.findByRole('heading', {level: 1, name: 'Sustainability Dashboard'})).toBeInTheDocument();
    expect(screen.getByText('Software Engineering Capstone · Spring 2026')).toBeInTheDocument();
    expect(screen.queryByText("We couldn't find this project")).toBeNull();
  });
});
