import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {PresentingTeamsPage} from '@/routes/PresentingTeamsPage/PresentingTeamsPage';

// The real view and grid, over a schedule request that fails or finds nothing.
const {mockFetchCurrentSchedule} = vi.hoisted(() => ({mockFetchCurrentSchedule: vi.fn()}));

vi.mock('@/features/events/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/events/api')>()),
  fetchCurrentSchedule: (...args: unknown[]) => mockFetchCurrentSchedule(...args),
}));

const httpError = (status: number) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {response: {status}});

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/presenting-teams']}>
      <PresentingTeamsPage />
    </MemoryRouter>,
  );

describe('PresentingTeamsPage states', () => {
  afterEach(() => {
    cleanup();
    mockFetchCurrentSchedule.mockReset();
  });

  it('names the presenting teams when the schedule cannot be loaded', async () => {
    mockFetchCurrentSchedule.mockRejectedValue(httpError(503));
    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "We couldn't load the presenting teams. Please try again.",
    );
    expect(screen.getByRole('button', {name: 'Try Again'})).toHaveClass('itg-btn-outline');
  });

  it('shows a heading, the text and Search Past Projects when no schedule is published', async () => {
    mockFetchCurrentSchedule.mockRejectedValue(httpError(404));
    renderPage();

    expect(await screen.findByRole('heading', {level: 2, name: 'No presenting teams yet'})).toBeInTheDocument();
    expect(
      screen.getByText(
        "Teams appear here once this semester's showcase schedule is published. Older projects are in Past Projects.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Search Past Projects'})).toHaveAttribute('href', '/past-projects');
  });
});
