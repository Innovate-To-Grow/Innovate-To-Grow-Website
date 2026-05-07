import {render} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import type {EventSchedulePayload, ScheduleSlot} from '../../features/events/api';
import {SchedulePage} from './SchedulePage';

const useCurrentEventScheduleMock = vi.fn();

vi.mock('../../features/events/useCurrentEventSchedule', () => ({
  useCurrentEventSchedule: () => useCurrentEventScheduleMock(),
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
        max_order: 3,
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
            slots: [slot(1, 'CSE-101'), slot(3, 'CSE-103')],
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
            slots: [slot(1, 'CSE-201')],
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

describe('SchedulePage', () => {
  beforeEach(() => {
    useCurrentEventScheduleMock.mockReset();
  });

  it('renders a full missing presentation row as Break while preserving partial missing cells as TBD', () => {
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

    expect(container.querySelectorAll('.schedule-presentation-break')).toHaveLength(2);
    expect(container.querySelectorAll('.schedule-presentation-empty')).toHaveLength(1);
  });
});
