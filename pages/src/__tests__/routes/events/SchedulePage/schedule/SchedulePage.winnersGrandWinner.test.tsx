import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SchedulePage} from '@/routes/events/SchedulePage/page/SchedulePage';
import {projectRow, schedulePayload, slot} from '@/__tests__/routes/events/SchedulePage/schedule/schedulePageFixtures';

const useCurrentEventScheduleMock = vi.fn();

vi.mock('@/features/events/hooks/useCurrentEventSchedule', () => ({
  useCurrentEventSchedule: (scheduleId?: string | null) => useCurrentEventScheduleMock(scheduleId),
}));

describe('SchedulePage', () => {
  beforeEach(() => {
    useCurrentEventScheduleMock.mockReset();
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 1024,
    });
    // jsdom does not implement scrollIntoView or matchMedia.
    Element.prototype.scrollIntoView = vi.fn();
    delete (window as {matchMedia?: unknown}).matchMedia;
  });

  afterEach(() => {
    cleanup();
  });

  it('renders winners and grand-winner awards', () => {
    const payload = schedulePayload();
    payload.show_winners = true;
    payload.grand_winners = [
      {section: 'CAP', winner: 'Grand Winner A'},
      {section: 'XYZ', winner: 'Grand Winner B'},
    ];
    payload.sections = [
      {
        ...payload.sections[0],
        id: 's-cap',
        code: 'CAP',
        label: 'Capstone',
        tracks: [
          {
            ...payload.sections[0].tracks[0],
            id: 'track-winner',
            track_number: 1,
            topic: 'AI',
            winner: 'Team Alpha',
            slots: [slot(1, 'CAP-101')],
          },
        ],
      },
    ];

    useCurrentEventScheduleMock.mockReturnValue({data: payload, loading: false, error: null});

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Winners!')).toBeInTheDocument();
    expect(screen.getByText('F3 Innovate Engineering Award:')).toBeInTheDocument();
    expect(screen.getByText('F3 Innovate Award:')).toBeInTheDocument();
    expect(screen.getByText('Grand Winner A')).toBeInTheDocument();
    expect(screen.getByText('Grand Winner B')).toBeInTheDocument();
    expect(screen.getByText('Team Alpha')).toBeInTheDocument();
  });

  it('renders expo and awards agenda items', () => {
    const payload = schedulePayload();
    payload.expo = {
      title: 'Expo',
      location: 'Hall A',
      items: [{id: 'expo-1', time: '10:00', title: 'Booths', location: 'Hall A'}],
    };
    payload.awards = {
      title: 'Awards',
      location: 'Main Stage',
      items: [{id: 'award-1', time: '11:00', title: 'Ceremony', location: 'Main Stage'}],
    };

    useCurrentEventScheduleMock.mockReturnValue({data: payload, loading: false, error: null});

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Hall A')).toBeInTheDocument();
    expect(screen.getByText('Booths')).toBeInTheDocument();
    expect(screen.getByText('Main Stage')).toBeInTheDocument();
    expect(screen.getByText('Ceremony')).toBeInTheDocument();
  });

  it('sets the team search param when a team link is clicked', () => {
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    const LocationProbe = () => {
      const location = useLocation();
      return <div data-testid="location-probe">{location.search}</div>;
    };

    render(
      <MemoryRouter initialEntries={['/schedule']}>
        <SchedulePage />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'CSE-101'}));

    expect(screen.getByTestId('location-probe')).toHaveTextContent('value=CSE-101');
    expect(screen.getByPlaceholderText('Search projects…')).toHaveValue('CSE-101');
  });

  it('filters the projects grid down to presenting projects', () => {
    const payload = schedulePayload();
    payload.projects = [
      projectRow({id: 'project-1', team_number: 'CSE-101', project_title: 'Smart Grid'}),
      projectRow({id: 'project-2', team_number: 'CSE-102', project_title: 'Hidden Project', is_presenting: false}),
    ];

    useCurrentEventScheduleMock.mockReturnValue({data: payload, loading: false, error: null});

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(screen.getAllByText('Smart Grid').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('Hidden Project')).not.toBeInTheDocument();
  });

  it('selects a team from the mobile schedule cards', () => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 500,
    });
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getAllByRole('button', {name: 'CSE-101'})[0]);

    expect(screen.getByPlaceholderText('Search projects…')).toHaveValue('CSE-101');
  });
});
