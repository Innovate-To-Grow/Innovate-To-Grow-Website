import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter, Route, Routes} from 'react-router';

import {ProjectDetailPage} from '@/routes/ProjectDetailPage/ProjectDetailPage';
import {fetchProjectDetail} from '@/features/projects/api';
import {fetchCurrentSchedule} from '@/features/events/api';
import {
  HVAC_PROJECT_ID,
  HVAC_SLOT_ID,
  WING_PROJECT_ID,
  currentSchedulePayload,
} from '@/__tests__/features/projects/fixtures/currentSchedule';

vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: vi.fn(),
}));

vi.mock('@/features/events/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/events/api')>()),
  fetchCurrentSchedule: vi.fn(),
}));

const notFoundError = () => Object.assign(new Error('Request failed with status code 404'), {response: {status: 404}});

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
        <Route path="/past-projects/project/:id" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

const projectDetail = {
  id: '11111111-1111-4111-8111-111111111111',
  project_title: 'Rotary Joint Testing System',
  team_name: 'General Rotary',
  team_number: '101',
  organization: 'E&J Gallo Winery',
  industry: 'Food Processing',
  abstract: 'A detailed abstract.',
  student_names: 'Alice, Bob',
  class_code: 'CAP',
  track: null,
  presentation_order: null,
  semester_label: '2025 Spring',
};

describe('ProjectDetailPage', () => {
  beforeEach(() => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockResolvedValue(projectDetail);
    // The schedule of this semester, which has none of the archive ids used below.
    vi.mocked(fetchCurrentSchedule).mockReset();
    vi.mocked(fetchCurrentSchedule).mockResolvedValue(currentSchedulePayload());
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows a current project from the schedule, by the id Current Projects links to', async () => {
    // As in production, the archive does not know current-semester ids.
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/projects/${HVAC_PROJECT_ID}`);

    expect(
      await screen.findByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'}),
    ).toBeInTheDocument();
    expect(screen.getByText('Engineering Capstone · Spring 2026')).toHaveClass('itg-eyebrow');
    expect(screen.getByText('HVAC Regulators · ASHRAE - Sierra Delta')).toHaveClass('itg-page-meta');
    expect(screen.getAllByRole('term').map((term) => term.textContent)).toEqual([
      'Term',
      'Class',
      'Team #',
      'Team',
      'Organization',
      'Industry',
      'Showcase',
    ]);
    expect(screen.getAllByRole('definition').map((value) => value.textContent)).toEqual([
      'Spring 2026',
      'Engineering Capstone (CAP)',
      '101',
      'HVAC Regulators',
      'ASHRAE - Sierra Delta',
      'Energy',
      'Track 1 · 1:00 · Glacier 165',
    ]);
    expect(screen.getByText(/^This project aimed to design a complete HVAC system/)).toHaveClass(
      'project-detail-abstract',
    );
    const members = screen.getByRole('heading', {level: 2, name: 'Team members'}).closest('section') as HTMLElement;
    expect(within(members).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Brian Arroyo',
      'Joel Gonzalez',
      'Kyle On',
      'Manuel Cruz Cavero',
    ]);
    const backLinks = screen.getAllByRole('link', {name: /back to current projects/i});
    expect(backLinks).toHaveLength(2);
    backLinks.forEach((link) => expect(link).toHaveAttribute('href', '/current-projects'));
    expect(screen.queryByRole('heading', {name: "We couldn't find this project"})).toBeNull();
    expect(fetchProjectDetail).not.toHaveBeenCalled();
  });

  it('shows a current team that is not presenting, with the term of the schedule', async () => {
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/projects/${WING_PROJECT_ID}`);

    expect(
      await screen.findByRole('heading', {level: 1, name: 'Distributed-Flapping Wing with Glide-Lock Mechanism'}),
    ).toBeInTheDocument();
    expect(screen.getByText('Engineering Capstone · Spring 2026')).toHaveClass('itg-eyebrow');
    expect(screen.getByText('Showcase').nextElementSibling).toHaveTextContent(/^Not presenting$/);
    expect(screen.getByText('Abstract-201')).toBeInTheDocument();
    // No student names on this row: no empty Team members section.
    expect(screen.queryByRole('heading', {name: 'Team members'})).toBeNull();
  });

  it('falls back to the archive for an archive id on /projects/:id', async () => {
    renderAt(`/projects/${projectDetail.id}`);

    expect(await screen.findByRole('heading', {name: 'Rotary Joint Testing System'})).toBeInTheDocument();
    expect(fetchCurrentSchedule).toHaveBeenCalledTimes(1);
    expect(fetchProjectDetail).toHaveBeenCalledWith(projectDetail.id, expect.any(AbortSignal));
  });

  it('reads only the archive on past-project pages, even for an id the schedule has', async () => {
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/past-projects/project/${HVAC_PROJECT_ID}`);

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
    expect(fetchCurrentSchedule).not.toHaveBeenCalled();
  });

  it.each(['/projects/archive', '/projects/past', '/past-projects/project/archive', '/projects/..%2Fpast-shares'])(
    'says %s is not a project, without requesting the list endpoint its name matches',
    async (path) => {
      renderAt(path);

      expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
      expect(fetchCurrentSchedule).not.toHaveBeenCalled();
      expect(fetchProjectDetail).not.toHaveBeenCalled();
    },
  );

  it('does not take a schedule slot id for a project', async () => {
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/projects/${HVAC_SLOT_ID}`);

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
  });

  it('offers to try again, instead of calling the link wrong, when the schedule cannot be read', async () => {
    vi.mocked(fetchCurrentSchedule).mockRejectedValueOnce(new Error('Network Error'));
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    renderAt(`/projects/${HVAC_PROJECT_ID}`);

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't load this project"})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {name: "We couldn't find this project"})).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: 'Try Again'}));

    expect(
      await screen.findByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'}),
    ).toBeInTheDocument();
    expect(fetchCurrentSchedule).toHaveBeenCalledTimes(2);
  });
});
