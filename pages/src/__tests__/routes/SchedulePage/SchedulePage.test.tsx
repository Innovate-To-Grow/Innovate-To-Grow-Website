import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {EventSchedulePayload, ScheduleProjectRow, ScheduleSlot} from '@/features/events/api';
import {SchedulePage} from '@/routes/SchedulePage/SchedulePage';

const useCurrentEventScheduleMock = vi.fn();

vi.mock('@/features/events/hooks/useCurrentEventSchedule', () => ({
  useCurrentEventSchedule: (scheduleId?: string | null) => useCurrentEventScheduleMock(scheduleId),
}));

function slot(order: number, teamNumber: string): ScheduleSlot {
  return {
    id: `${teamNumber}-${order}`,
    order,
    is_break: false,
    display_text: teamNumber,
    team_number: teamNumber,
    team_name: '',
    project_title: '',
    organization: '',
    industry: '',
    abstract: '',
    student_names: '',
    tooltip: '',
    project_id: null,
  };
}

function breakSlot(order: number, trackId: string): ScheduleSlot {
  return {
    id: `break-${trackId}-${order}`,
    order,
    is_break: true,
    display_text: 'Break',
    team_number: '',
    team_name: '',
    project_title: '',
    organization: '',
    industry: '',
    abstract: '',
    student_names: '',
    tooltip: '',
    project_id: null,
  };
}

function schedulePayload(): EventSchedulePayload {
  return {
    event: {
      id: 'schedule-1',
      name: 'Demo Day',
      slug: 'demo-day',
      date: 'May 7, 2026',
      location: 'Conference Center',
      description: 'Presentation schedule',
    },
    show_winners: false,
    grand_winners: [],
    expo: {
      title: 'Expo',
      location: '',
      items: [],
    },
    presentations_title: 'PRESENTATIONS',
    sections: [
      {
        id: 'section-cse',
        code: 'CSE',
        label: 'Computer Science',
        display_order: 1,
        start_time: '1:00',
        slot_minutes: 30,
        accent_color: '#002856',
        max_order: 4,
        tracks: [
          {
            id: 'track-1',
            track_number: 1,
            label: 'Track 1',
            room: 'Room 101',
            zoom_link: '',
            topic: 'Software',
            winner: '',
            display_order: 1,
            slots: [slot(1, 'CSE-101'), breakSlot(2, 'track-1'), slot(3, 'CSE-103')],
          },
          {
            id: 'track-2',
            track_number: 2,
            label: 'Track 2',
            room: 'Room 102',
            zoom_link: '',
            topic: 'Systems',
            winner: '',
            display_order: 2,
            slots: [slot(1, 'CSE-201'), breakSlot(2, 'track-2')],
          },
        ],
      },
    ],
    awards: {
      title: 'Awards',
      location: '',
      items: [],
    },
    projects: [],
  };
}

function projectRow(overrides: Partial<ScheduleProjectRow> = {}): ScheduleProjectRow {
  return {
    id: 'project-1',
    track: 1,
    order: 1,
    year_semester: '2026 Spring',
    class_code: 'CSE',
    team_number: 'CSE-101',
    team_name: 'Team Alpha',
    project_title: 'Smart Grid',
    organization: 'Acme',
    industry: 'Energy',
    abstract: 'A smart grid project.',
    student_names: 'Alice, Bob',
    is_presenting: true,
    tooltip: '',
    ...overrides,
  };
}

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

  it('renders full missing presentation rows as Break while leaving partial missing cells blank', () => {
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    const {container} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    const rows = container.querySelectorAll('tbody tr');

    expect(container.querySelectorAll('.schedule-presentation-break')).toHaveLength(4);
    expect(rows[0]).toHaveTextContent('CSE-101');
    expect(rows[0]).toHaveTextContent('CSE-201');
    expect(rows[1]).toHaveTextContent('Break');
    expect(rows[2]).toHaveTextContent('CSE-103');
    expect(rows[2]).not.toHaveTextContent('TBD');
    expect(rows[3]?.querySelectorAll('.schedule-presentation-break')).toHaveLength(2);
    expect(rows[3]).toHaveTextContent('Break');
    expect(rows[3]).not.toHaveTextContent('TBD');
  });

  it('uses the same missing slot rendering rules in the mobile schedule cards', () => {
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

    const {container} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    const cards = container.querySelectorAll('.schedule-mobile-card');

    expect(container.querySelectorAll('.schedule-mobile-break')).toHaveLength(4);
    expect(cards[0]).toHaveTextContent('CSE-103');
    expect(cards[1]).not.toHaveTextContent('2:00TBD');
    expect(cards[0]).toHaveTextContent('2:30Break');
    expect(cards[1]).toHaveTextContent('2:30Break');
  });

  it('passes an explicit schedule id into the schedule hook', () => {
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    render(
      <MemoryRouter>
        <SchedulePage scheduleId="schedule-123" />
      </MemoryRouter>,
    );

    expect(useCurrentEventScheduleMock).toHaveBeenCalledWith('schedule-123');
  });

  it('uses schedule_id from the URL when no prop is provided', () => {
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    render(
      <MemoryRouter initialEntries={['/schedule?schedule_id=schedule-query']}>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(useCurrentEventScheduleMock).toHaveBeenCalledWith('schedule-query');
  });

  it('renders the loading state', () => {
    useCurrentEventScheduleMock.mockReturnValue({data: null, loading: true, error: null});

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Loading schedule...')).toBeInTheDocument();
  });

  it('renders the error state and its unavailable fallback', () => {
    useCurrentEventScheduleMock.mockReturnValue({data: null, loading: false, error: 'Backend unavailable'});

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Backend unavailable')).toBeInTheDocument();
  });

  it('falls back to the unavailable message when there is neither data nor error', () => {
    useCurrentEventScheduleMock.mockReturnValue({data: null, loading: false, error: null});

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Event schedule is unavailable.')).toBeInTheDocument();
  });

  it('switches to the mobile grid when the media query fires', () => {
    const listeners = new Map<string, (event: {matches: boolean}) => void>();
    const mql = {
      matches: false,
      addEventListener: vi.fn((event: string, callback: (e: {matches: boolean}) => void) => {
        listeners.set(event, callback);
      }),
      removeEventListener: vi.fn(),
    };
    (window as unknown as {matchMedia: unknown}).matchMedia = vi.fn().mockReturnValue(mql);

    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    const {container} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(container.querySelector('.schedule-presentation-table')).toBeInTheDocument();
    expect(container.querySelector('.schedule-page-mobile-grid')).not.toBeInTheDocument();

    act(() => {
      listeners.get('change')?.({matches: true});
    });

    expect(container.querySelector('.schedule-page-mobile-grid')).toBeInTheDocument();
    expect(container.querySelector('.schedule-presentation-table')).not.toBeInTheDocument();
  });

  it('sorts sections by known order, then display order, breaking ties by display order', () => {
    const payload = schedulePayload();
    const baseSection = payload.sections[0];
    payload.sections = [
      {...baseSection, id: 's-zzz', code: 'ZZZ', label: 'Unknown', display_order: 0},
      {...baseSection, id: 's-cap-a', code: 'CAP', label: 'Cap A', display_order: 5},
      {...baseSection, id: 's-cap-b', code: 'CAP', label: 'Cap B', display_order: 3},
    ];

    useCurrentEventScheduleMock.mockReturnValue({data: payload, loading: false, error: null});

    const {container} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    const headings = container.querySelectorAll('.schedule-presentation-heading');
    expect([...headings].map((heading) => heading.textContent)).toEqual([
      'Cap B (CAP)',
      'Cap A (CAP)',
      'Unknown (ZZZ)',
    ]);
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
    expect(screen.getByPlaceholderText('Search projects...')).toHaveValue('CSE-101');
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

    expect(screen.getByPlaceholderText('Search projects...')).toHaveValue('CSE-101');
  });

  it('clears the team search param when a slot has no team identifier', () => {
    const payload = schedulePayload();
    const baseTrack = payload.sections[0].tracks[0];
    payload.sections = [
      {
        ...payload.sections[0],
        tracks: [
          {
            ...baseTrack,
            slots: [{...slot(1, 'CSE-101'), team_number: '', display_text: ''}],
          },
        ],
      },
    ];
    useCurrentEventScheduleMock.mockReturnValue({data: payload, loading: false, error: null});

    const LocationProbe = () => {
      const location = useLocation();
      return <div data-testid="location-probe">{location.search}</div>;
    };

    const {container} = render(
      <MemoryRouter initialEntries={['/schedule?value=CSE-101']}>
        <SchedulePage />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(container.querySelector('.schedule-presentation-team')!);

    expect(screen.getByTestId('location-probe')).toHaveTextContent('');
  });

  it('renders TBD placeholders and slot organizations', () => {
    const payload = schedulePayload();
    const [trackOne, trackTwo] = payload.sections[0].tracks;
    payload.sections = [
      {
        ...payload.sections[0],
        tracks: [
          {
            ...trackOne,
            room: '',
            topic: 'AI',
            slots: [{...slot(1, 'CSE-101'), organization: 'Acme Corp'}],
          },
          {
            ...trackTwo,
            room: 'Room 102',
            topic: '',
            slots: [slot(1, 'CSE-201')],
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

    expect(screen.getAllByText('TBD').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });
});
