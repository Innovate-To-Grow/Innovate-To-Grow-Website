import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter, Route, Routes} from 'react-router';

import {ProjectDetailPage} from '@/routes/ProjectDetailPage/ProjectDetailPage';
import {fetchProjectDetail} from '@/features/projects/api';
import {fetchCurrentSchedule} from '@/features/events/api';
import {
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

  it('explains a project that does not exist and offers a search', async () => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValue({response: {status: 404}});
    render(
      <MemoryRouter initialEntries={['/projects/missing']}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
    expect(screen.getByText(/The link may be incomplete, or the project has been removed/)).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 1}).closest('section')).toHaveAttribute('data-launcher-avoid', '');
    // One primary action, then a text link.
    const search = screen.getByRole('link', {name: 'Search Past Projects'});
    expect(search).toHaveAttribute('href', '/past-projects');
    expect(search).toHaveClass('itg-btn', 'itg-btn-primary');
    const current = screen.getByRole('link', {name: 'Current Projects'});
    expect(current).toHaveAttribute('href', '/current-projects');
    expect(current).toHaveClass('itg-link');
    expect(screen.getByRole('link', {name: /back to current projects/i})).toHaveAttribute('href', '/current-projects');
    expect(screen.queryByRole('button', {name: 'Try Again'})).toBeNull();
    // The mark is claimed in an effect, which can run after the heading that findByRole saw.
    await waitFor(() =>
      expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex'),
    );
  });

  it.each([
    ['/projects', '22222222-2222-4222-8222-222222222222'],
    ['/projects', 'archive'],
    ['/past-projects/project', '22222222-2222-4222-8222-222222222222'],
    ['/past-projects/project', 'not-a-project'],
  ])('keeps an unknown project at %s/%s out of search results', async (prefix, id) => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValue(notFoundError());
    // Not the title an earlier case left: this page has to set it.
    document.title = 'Innovate to Grow | School of Engineering';
    renderAt(`${prefix}/${id}`);

    expect(await screen.findByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeInTheDocument();
    // The title and the mark are set in effects, which can run after the heading that findByRole saw.
    await waitFor(() => expect(document.title).toBe('Project not found | Innovate to Grow'));
    await waitFor(() =>
      expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex'),
    );
    cleanup();
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });

  it('shows an error message with the Past Projects back link when the fetch fails', async () => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValue(new Error('boom'));
    render(
      <MemoryRouter initialEntries={[`/past-projects/project/${projectDetail.id}`]}>
        <Routes>
          <Route path="/past-projects/project/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    // Any failure but a 404 lands here, a server error included: the copy does not blame the visitor's connection.
    expect(
      await screen.findByText(
        'Unable to load this project. Please try again, or search for it by title, team or organization.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/connection/i)).toBeNull();
    expect(screen.getByRole('heading', {level: 1, name: "We couldn't load this project"})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {name: 'Rotary Joint Testing System'})).toBeNull();
    const backLink = screen.getByRole('link', {name: /back to past projects/i});
    expect(backLink.getAttribute('href')).toBe('/past-projects');
    // Try Again is the page's one primary action; the ways out are text links.
    expect(screen.getByRole('button', {name: 'Try Again'})).toHaveClass('itg-btn', 'itg-btn-primary');
    const search = screen.getByRole('link', {name: 'Search Past Projects'});
    expect(search).toHaveAttribute('href', '/past-projects');
    expect(search).toHaveClass('itg-link');
    expect(search).not.toHaveClass('itg-btn');
    expect(screen.getByRole('link', {name: 'Current Projects'})).toHaveClass('itg-link');
    // The two links wrap as one group, so a phone never leaves one alone under the button and the other.
    const links = search.parentElement as HTMLElement;
    expect(links).toHaveClass('project-detail-error-links');
    expect(links).toContainElement(screen.getByRole('link', {name: 'Current Projects'}));
    expect(links.previousElementSibling).toBe(screen.getByRole('button', {name: 'Try Again'}));
  });

  it('keeps a failed load out of search results until a retry loads the project', async () => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValueOnce(new Error('boom')).mockResolvedValue(projectDetail);
    renderAt(`/past-projects/project/${projectDetail.id}`);
    const robots = () => document.head.querySelector('meta[name="robots"]');

    // The mark is claimed and withdrawn in effects, which can run after the DOM change findByRole saw.
    const tryAgain = await screen.findByRole('button', {name: 'Try Again'});
    await waitFor(() => expect(robots()).toHaveAttribute('content', 'noindex'));
    fireEvent.click(tryAgain);

    expect(await screen.findByRole('heading', {level: 1, name: 'Rotary Joint Testing System'})).toBeInTheDocument();
    await waitFor(() => expect(robots()).toBeNull());
  });

  it('shows the current-projects back link on the error branch of the legacy route', async () => {
    vi.mocked(fetchProjectDetail).mockReset();
    vi.mocked(fetchProjectDetail).mockRejectedValue(new Error('boom'));
    render(
      <MemoryRouter initialEntries={[`/projects/${projectDetail.id}`]}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Unable to load this project\./)).toBeInTheDocument();
    const backLink = screen.getByRole('link', {name: /back to current projects/i});
    expect(backLink.getAttribute('href')).toBe('/current-projects');
  });
});
