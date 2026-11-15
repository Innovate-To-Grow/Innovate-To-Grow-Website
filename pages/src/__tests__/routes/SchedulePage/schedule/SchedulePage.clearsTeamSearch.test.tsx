import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SchedulePage} from '@/routes/SchedulePage/schedule/SchedulePage';
import {schedulePayload, slot} from '@/__tests__/routes/SchedulePage/schedule/schedulePageFixtures';

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
